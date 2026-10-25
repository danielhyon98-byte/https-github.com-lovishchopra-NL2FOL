# External review fixes (Update 7, 12 October 2026)

This release closes the nine findings of the external review of 12 October 2026 that still reproduced, and the two
evaluation items it raised. Every finding was fixed at its cause, given regression tests, and accepted by an independent
verification that re-ran the reviewer's own probes, the acceptance criteria and new probes. Five verifications were
needed; the last accepted all twelve items (nine findings, two evaluation items, and the general rule that no test was
weakened and no non-success is shown as success) with no violation.

Scope: these results prove properties of the encodings and of this code only. No live model provider was called;
translation fidelity was not re-measured on live translations (the arena counts below are transport over recorded
fixtures). Nothing here has been deployed.

## Versions

| Component | Before | After |
| --- | --- | --- |
| engine | 0.3.0 | 0.4.0 |
| policy | 2026.10-v3 | 2026.10-v4 |
| translator | 0.3.0 | 0.4.0 |
| integration contract | 0.1 | 0.2 |

Every result now also binds the computed identity of the build that produced it (`build_id`, `schema_id`,
`policy_id`), so a result from another build can never look current even if a version string was not bumped.

## Findings

| # | Finding | What changed | Where |
| --- | --- | --- | --- |
| 1 | Exact claims were repaired into approximate ones, so a solver success could be earned by widening an exactly stated figure | Exactness is read from the source wording, never from the solver. A written calculation is computed as written by a closed arithmetic reader over exact fractions (nothing is evaluated as code). A figure counts as a calculation result only when the calculation ends at its `=`; words such as "then", "implies" or "we get" are never read as units. A widened retry is recorded as weaker and blocks release. | `translate/quantities.py`, `translate/precision.py`, `translate/pipeline.py` |
| 2 | Model-chosen trusted grounding kinds (`arithmetic_fact`, `task_setting`, `rubric_rule`) hid unsupported premises (for example a 120 km distance replaced by 160 km) | Only a record created by a check in this process confers task or source authority; a payload's own `verified=True` is discarded (E505). Every relied-on premise no check validated is listed in `unverified_dependencies`. A new release check refuses any result with an ungrounded or unverified dependency. A check that only finds a premise's numbers in the task no longer approves an invented relation. | `engine/authority.py`, `engine/release.py`, `translate/grounding.py` |
| 3 | `produce_unsat_core=False` removed dependency evidence and bypassed E108 | The unsat core is always extracted (no extra cost); the flag now only controls whether the raw core is serialised. Dependencies, E108 and E112 are always derived. | `engine/procedures.py`, `engine/runner.py` |
| 4 | The reviewer did not see the original evidence | The review request carries the task, supporting claims, supplied texts (bounded, cuts recorded), source identities and the premise-to-source mapping, and is bound to them; a changed source makes an earlier review stale. | `translate/review.py` |
| 5 | A genuinely signed result from an earlier release passed current binding checks | Build, schema and policy identities are computed and bound. Earlier results still parse and keep valid signatures (inspectable) but are never current: the release check, the binding check (INT-STALE-005), the outcome composer and cross-checks refuse them. | `engine/identity.py`, `engine/provenance.py`, `integrity/cross_check.py` |
| 6 | E110/E111 withheld valid counterexamples | A definition or an unconstrained symbol is rejected only with source-linked evidence that a source (the claim, a supporting claim, a supplied text or the task record) asserts the omitted figure; a non-asserting phrasing keeps the advisory W110/W111 and shows the counterexample. A sentence that starts with a lower-case variable is split correctly. | `engine/runner.py`, `translate/coverage.py` |
| 7 | A partially checked reference list was marked verified | Every reference is validated separately; an unknown document or an unlocatable reference fails or stays unchecked, and only complete support verifies a premise. | `translate/grounding.py` |
| 8 | Effective validation limits were absent from the result binding | A `limits_digest` is bound whenever the effective limits differ from the policy's defaults; a default receiver refuses a permissive result. | `engine/results.py`, `engine/provenance.py` |
| 9 | Numeric grounding depended on notation | Source figures are read as typed exact quantities (per cent, number words, scale words, currency, units); a literal grounds as written or through one recorded derivation. A rounded given such as "x is 0.33 to 2 decimal places" grounds both transcribed exactly and at its stated tolerance. | `translate/quantities.py` |

## Evaluation items

- **Separate measures.** The arena report no longer leads with one functional rate: transport, fixture coverage,
  translation fidelity and claim measures are reported separately, each with its own denominator, and recorded
  translations that were not served are shown with their reason (`scripts/arena/run_arena.py`).
- **Timing-sensitive parser test.** Stabilised without relaxing its bound: a warm-up run, caches emptied before every
  measured run, the heap frozen during it, and the median taken (`tests/timing.py`).

## Behaviour that became more conservative

Some calculation readings are now treated as unstated rather than guessed, which is the safe direction (an ambiguity,
never a manufactured verdict): a count noun ending a calculation (`5 apples + 3 apples = 8`), a unit conversion written
with no operator (`25.0 cm³ = 0.0250 dm³`), `ms⁻¹` written for `m s⁻¹`, and a plain function value (`ln 2 = 0.693`).
`0.33 ≈ 1/3` no longer reads 0.33 as rounded, because a sign governs only the figure after it.

## Verification

- Full suite: 5264 passed, 45 deselected (the stress selection, not run by instruction), 4 expected failures.
- Every recorded arena round replayed on fresh copies: r1 30/30, r1-adv 150/151 (the planted empty answer stays
  rejected), r2 46/46, r3 46/46, r4 46/46, r5 46/46, r6 46/46, r7 177/177. Each round is identical field by field to
  the previous repair's replay; compared with the code before these fixes, the only differences are the documented
  dependency lists (r5: 7 records, r7: 6 records).
- Every new or rewritten test asserts the stricter rule; no test was weakened, skipped or deleted.

# Argument diagnosis round: the evidence family, its false alarms and the security fixes (policy 2026.10-v5)

This part of the argument-diagnosis round (rules `argdiag-1`) gives the evidence family its rules, removes the evidence
false alarms of the development corpus, applies the security fixes of the design's section C and fixes the confirmed
review-lens findings of this area. Every change only adds information or withholds a verification that no check
established: no status is upgraded, no non-success is shown as success, and a diagnostic can only make a result less
releasable.

Scope: these results prove properties of the encodings and of this code only. No live model provider was called, and
nothing here has been deployed. The development corpus was measured; the held-out corpus was not read.

## Authority and circularity (issue 1)

| Change | Where |
| --- | --- |
| Only a check in this process confers authority, for circularity too: `assumed_grounding(g)` is `not has_authority(g)`, so "p, therefore p" with nothing but a source or task label behind p is circular (`E112`) under every kind, and a transcription only when a check verified p against the supplied text or the task record. `dependency_policy()` records `assumed_for_circularity: "not_established"`. | `engine/authority.py` |
| A task-authority premise that states no figure and has no excerpt is unvalidated (`verified=None`), never refuted: no record was checked. | `translate/grounding.py` |
| A located excerpt verifies a proposition only as a literal: joined to the writer's own proposition with "and", "or", "if" or "iff" it stays unverified, so restating the point through it is circular (f07). | `translate/grounding.py` |

## The evidence family

`translate/diag_evidence.py` holds the claim rules `EVD-SRC-001`, `EVD-SRC-003`, `EVD-SRC-004`, `EVD-LACK-001`,
`EVD-FIG-001`, `EVD-AUTH-001` and `EVD-CHERRY-001`, and the report rules `EVD-SRC-002` and `EVD-LACK-002` (info only:
"not checked", never "false"). They grade the premises the point needs, read authority from this process's grounding
records only, and are shown at warning only when the request names supplied material as the basis of the answer
(`source_bound`; info with `capped_from` otherwise). All twelve evidence defects of the development corpus are named.

## False alarms removed

| Control | It was named | Fix | Where |
| --- | --- | --- | --- |
| c01, c01b, c02 (history quotes), c04 (English quote) | INT-LEDGER-020 | a source excerpt is compared with every excerpt the synthesized claim keeps under the same (document, locator) | `integrity/ledger.py` |
| c02 (modus tollens) | a failed grounding | a figureless task premise is unvalidated, not refuted | `translate/grounding.py` |
| e2e-B5-sp | INT-REQ-003, CORE-SRC-003 | quotation roles: in a marking, feedback, correction or editing task the corrected form after an arrow (or "should be", "change ... to", a "Model:" label) is a correction, never a quotation; in any other task such a span stays a quotation and is checked (repair round 4, INV-Q1) | `adapters/markdown.py` |
| e2e-B6-en | INT-REQ-003, ES-SRC-001 | a quoted function word, or a short span after a negating frame (`without "like" or "as"`), is a mention | `adapters/markdown.py` |
| e2e-B13-sp | INT-REQ-003 | emphasis markup wrapping a whole excerpt is set aside when the marked form is not found | `adapters/sources.py` |
| e2e-B16-ess | a failed grounding | a figure written as a calculation's result, or after "≈", states the half-unit enclosure of its last written place (superscript and caret notation alike); a given figure still states no interval | `translate/grounding.py`, `translate/quantities.py` |
| e2e-B23-bm | a failed grounding | a relation's figure that the cited document states outside the excerpt leaves the relation unverified, not refuted; a figure the request states as a given, cited to a document that does not hold it, is re-checked against the task record ("stated by the request, cited as doc-luma"); a figure in the request's question, condition, negation or answer requirement is no given | `translate/grounding.py` |

## Security (design section C) and the review-lens findings

| Finding | Change | Where |
| --- | --- | --- |
| B26 / SEC-1 | identifiers, assertion ids and literals are matched whole (`fullmatch`): `x\n` is no second symbol, `P1\n` no impersonating premise id; the request-id header too | `ir/schema.py`, `engine/validator.py`, `service/app.py` |
| SEC-3 | the code fence is found by a linear scan (a run of backticks is one step); provider text over 64 KiB is refused before parsing | `translate/parsing.py` |
| SEC-4 | every logged field is escaped and cut to 128 characters, on the service's logger and the translation pipeline's | `service/app.py` |
| SEC-6 | `POST /v1/outcomes` refuses client fixture responses (403 `E506`, before the body is read) unless `allow_client_fixtures` is set | `service/app.py`, `service/settings.py`, `engine/errors.py` |
| SEC-5 | `model_completion` is server-controlled; models are always completed | `service/app.py`, `engine/procedures.py` |
| SEC-8 | `adapter_id` is looked up in a closed allowlist; a refused id imports nothing | `service/app.py` |
| B27 (validator half) | a lone surrogate in a text payload is `E100` to the validator | `engine/validator.py` |
| SEC-7 | the diagnosis is reachable from Python only; the service always diagnoses and its release check refuses an undiagnosed result; a guard test bounds the derived runs on 128 premises | tests |
| formal-robustness-1 | the consistency precheck builds no model; each model value is bounded inside Z3 before any text of it is built (beyond 400 digits: UNKNOWN `E401`, never a cut value); the extraction is timed as its own stage | `engine/procedures.py` |
| robustness-and-contracts-4, -6 | a lone surrogate in provider output is a failed translation; in any HTTP body it is 400 `E100`, never a 500 | `translate/parsing.py`, `service/app.py` |
| robustness-and-contracts-11 | `config` and the outcome route's `report` are validated strictly | `service/app.py` |
| fidelity-1 | a figure stated for another year than the symbol's grounds nothing | `translate/grounding.py` |
| security-2 | a relayed specialist's report confers no authority (`peer_report`) | `translate/grounding.py`, `adapters/sources.py` |
| combinator-faults-3 | `INT-LEDGER-029`: a synthesis that states a verification status of the answer is a self-report | `integrity/ledger.py` |
| combinator-faults-4 | `INT-LEDGER-025` checks each evidence reference's excerpt against the text it names; `INT-LEDGER-030` names a document nothing in scope supplies or cites | `integrity/ledger.py` |
| combinator-faults-5 | a parenthetical description is no part of an author's name; the non-literary kinds ("the leaflet", "the textbook", "the case study") credit a text | `adapters/sources.py` |
| combinator-faults-7 | a verbatim copy changes nothing (`aligned_changes(t, t) == ([], [])`); a source sentence is aligned only with its best match | `integrity/ledger.py` |
| combinator-faults-8 | a minus glyph and the ASCII hyphen-minus are one sign | `integrity/ledger.py` |
| parser-safety-3 | the note-clause reader is linear on long whitespace runs | `adapters/markdown.py` |
| parser-safety-14 | a figure of thousands of digits never ends the ledger check | `integrity/ledger.py` |

## Tests rewritten to a stricter rule

- `tests/engine/test_round7_engine.py`: the restated task setting is two tests: validated by the task record it is a
  transcription (no `E112`), label-only it is a circle (`E112`).
- `tests/engine/test_overseer_round1.py`, `tests/translate/test_overseer_round1.py`,
  `tests/translate/test_review_2026_10_12_translate.py`, `tests/translate/test_round7_translate.py`: a label-only premise
  that restates the conclusion is now circular, and each test also pins that the same premise verified by a check is a
  transcription.
- `tests/contract/test_quotation_stub.py`: with the roles filled in, the role of every recorded span is pinned.
- `tests/engine/test_pack_policies.py`: the strict xfail marker on the trailing-newline test is removed (it passes). The
  marker on the lone-surrogate test stays, with its reason updated: the validator half is fixed, and the remaining
  cause is in a frozen file (below).
- `tests/branches/data/quant_general_reference.json`: one digest repinned, with its reason in the file's note (a
  quoted grammatical term is a mention; the quantity checks are unchanged).

No test was weakened, skipped or deleted.

## Verification

- Development corpus (101 cases, the scoring of the argument-diagnosis design): on the contract commit 9 named, 25
  caught but unnamed, 10 missed, 41 false alarms and 16 clean controls; on the Phase 0 base 9, 26, 9, 40 and 17; after
  this round 18, 18, 8, 30 and 27. No case regressed: nine defects became named (the eight evidence defects that were
  caught unnamed, and f07, which was missed) and ten controls became clean (the table above). The remaining false
  alarms carry codes of the other families' rules (INT-SUBJ-001, INT-REQ-004 and -005, the constraint checks, a displayed
  counterexample, INT-HIST-001, PS-SRC-001, ES-STR-001, INT-CONFLICT-001, CORE-QNT-001).
- Every recorded arena round replayed on fresh copies, against the Phase 0 base replayed the same way: transport is
  unchanged (r1 30/30, r1-adv 150/151 with the planted empty answer still rejected, r2 to r6 46/46, r7 177/177), and
  no integrity finding changed. The receipts differ in three documented ways: the release assessments of claims now
  name evidence defects (EVD-LACK-001, EVD-SRC-001, EVD-FIG-001; a replay calls no fidelity reviewer, so no release was
  permitted before either); thirteen premises that quote a relayed specialist's report are listed as ungrounded
  dependencies (r2, r3, r6, r7: a peer report confers no authority); and in r7 the claim p1-point of lit-t13, a task
  statement restated with nothing but its task label behind it, is refused as circular (`E112`, INVALID_FORMALIZATION
  where it was AMBIGUOUS_TRANSLATION) in its six records.
- Full suite on this branch: 5886 passed, 45 deselected (the stress selection, not run by instruction), 1 expected
  failure (the lone-surrogate test, until the frozen runner change below) and 1 failure (the core-pack test, until the
  `branches/packs.py` change below). With those two changes applied and the expected-failure marker removed, the full
  suite gives 5888 passed and 45 deselected.

## Handed to the integration step (files this round does not own)

The integration step applied every item below; each test named here passes ("Integration of the argument-diagnosis
round", at the end of this file).

- `engine/runner.py` (frozen): `_raw_digest` encodes the unparsed payload with `errors="surrogatepass"`; then remove
  the strict xfail on `test_a_lone_surrogate_in_a_text_payload_is_an_invalid_formalization`.
- `branches/packs.py`: the core pack's `mentions` also take the uncited spans
  (`adapters.markdown.uncited_quotation_spans`), so a recorded quoted function word is no unverifiable quotation
  (`tests/branches/test_r7_quant_packs.py::test_a_quotation_of_the_request_or_a_word_the_text_lacks_is_no_unverifiable_quotation`
  fails until then).
- `engine/provenance.py` (read-only): `verify_signature` returns False on a result holding a lone surrogate instead of
  raising.
- `translate/pipeline.py`: map `parsing.ProviderOutputTooLarge` to TRANSLATION_FAILED ("provider output too large", no
  retry; it is INVALID_FORMALIZATION after a retry today, also a non-success); and word the circularity refusal for
  policy 2026.10-v5: the restating premises have nothing a check in this process established behind them, whatever
  kind they claim (the message still lists only the writer's kinds and an unvalidated `arithmetic_fact`).
- `channel/bus.py`: the report and synthesis mappings are validated strictly (`"yes"` is no boolean).
- The remaining `^...$` validators applied with `match` (B26's sweep): `adapters/generic_structured.py` accepts
  `created_at` with a trailing newline (`RFC3339_RE.match`), and `translate/prompts/__init__.py` checks prompt names
  with `_NAME_RE.match`; both should use `fullmatch`. `integrity/contracts.py` strips a timestamp before matching it,
  so it needs no change.
- `adapters/stem_specialist/parser.py` (`_units`): the unit reader still runs an unanchored regular-expression search over a
  long whitespace run, so a STEM answer with 20,000 spaces in a sentence takes about 3.6 s to deliver (0.35 s at 5,000);
  History and English deliveries of the same answer take 0.2 s and 0.1 s.

# Integration of the argument-diagnosis round

The argument-diagnosis work (the shared contract of named diagnostics, the evidence family above, the argument family,
the STEM reference and diagnostics, the channel and response gate, and the re-run review fixes) was merged onto the
end-to-end fixes (`8a78efe`, "Fix the end-to-end simulation findings"), one change set at a time, keeping every fix of
each side. Every change only adds information or withholds a verification no check established. Scope: these results
prove properties of the encodings and of this code only; no live model provider was called, and nothing has been
deployed.

## Where two sides changed the same thing

| Area | Resolution |
| --- | --- |
| `docs/integration-contract.md` | the end-to-end fixes' 0.3 (the named engine policy over HTTP and on the command line) stays as committed; the named diagnostics are 0.4 |
| STEM checks (`stem/checks.py`, `stem/relations.py`, `stem/document.py`, `stem/to_ir.py`) | the end-to-end readings (the antilogarithm read as a concentration, described roots, exponential models, `mod` checks) and the review's and the argument diagnosis's readings (affine readings, the intent rule, unit companions, stated operations, rounding, systems) are all kept (`docs/STEM_DESIGN.md`, section 24.10) |
| `docs/STEM_DESIGN.md` | the end-to-end section keeps its number 21, which committed files cite; the STEM review sections are 22 and 23 and the argument diagnosis is 24 |
| `channel/bus.py` | the end-to-end synthesis vocabulary findings (INT-SYNTH-014) and the channel work's contract names and envelope roles are both kept |
| `scripts/arena/run_arena.py` | the end-to-end harness relays each synthesis as the JSON the router receives (B1, B1b); the channel work refused syntheses-file fields the format does not hold. Merged: every such field is carried into the relayed mapping, so the hub refuses it with a receipt (REJECTED, INT-REQ-009); a field the synthesis contract does hold but the format does not define (`materiality`, `formal_conclusion`, `conflicts`) would be accepted if relayed, so the harness refuses that synthesis itself and does not relay it. Either way the record names the fields and is not functional |
| `service/app.py` | the server-controlled configuration keys of the security fixes (`memory_max_mb`, `model_completion`) and the end-to-end envelope keys (`problem`, `config`, `policy`) |

## Handed-over changes applied

- From the evidence family (above): the core pack's `mentions` take the uncited quotation spans
  (`branches/packs.py`); provider output over 64 KiB is TRANSLATION_FAILED with no retry (`translate/pipeline.py`); the
  report and synthesis mappings are validated strictly (`channel/bus.py`, `_strict_contract`); `created_at` is matched
  whole (`adapters/generic_structured.py`); the STEM unit reader's accuracy marks are read in one linear pass
  (`branches/generic_parser.accuracy_marked`, used by `adapters/stem_specialist/parser.py`). The runner's digest and
  `verify_signature` items are covered by the re-run review fixes below, and the lone-surrogate test passes with its
  expected-failure marker removed.
- From the STEM work: the channel passes `task_agent_ids` to the STEM parser, counting only agents of the same branch
  (B17; physics with mathematics keeps plain ids); `strip_markup` reads emphasis in one linear pass.
- From the re-run review fixes: an absent `solver_config.memory_max_mb` reads back as `None`, so a signed result
  round-trips through an `exclude_none` dump (the expected-failure marker of
  `tests/engine/test_rerun_review_provenance.py` is removed); `course_level` stated as `null` reads as `"unknown"` on the
  request and the plan too; `verify_message` never raises; the English parser's sentence boundaries are read in one
  pass; the contract text of section 2, 4, 6, 7 and 9.

## Fixed at integration

- **The diagnosis section of a claim summary pushed a structural finding out of the bounded summary**: the English
  end-to-end example no longer named its ES-SRC-001 error. The section now gets the room the other lines leave, with
  blocking diagnostics first (`translate/outcome.py`; `tests/translate/test_summary_fit.py`).
- **B17 qualified the ids of every STEM branch** once the bus line was applied as handed over: the physics and
  mathematics end-to-end test got `m1.1@maths-specialist`. The set is now the answering agent's branch only.

## Tests rewritten to the merged or a stricter rule

Each docstring says why. No test was weakened, skipped or deleted.

- `tests/engine/test_argument_diagnostics.py`: f07 is refused by the translator as circular, and the engine form is
  asserted on the proposal as this process grounds it; a restated task or text premise is E112 with ARG-CIRC-001 when
  only its label stands behind it and neither once a check verified it (the authority rule); ARG-CIRC-002 is asserted on
  the De Morgan restatement, and a new test pins that a restatement in the engine's normal form is E112 with ARG-CIRC-001
  and no ARG-CIRC-002; the controls assert every argument code as before, and also that the evidence records they carry
  are shown at info, capped as not source-bound, and keep the claim from release.
- `tests/translate/test_argument_rules.py`: a restated task premise is a circular refusal unless the task record
  validates it.
- `tests/engine/test_pack_policies.py`, `tests/engine/test_rerun_review_provenance.py`: the strict expected-failure
  markers are removed; the tests are unchanged and pass.
- `tests/service/test_named_policy_over_http.py`: the recorded configuration with its server-controlled options is
  asserted refused (400 E100); the replay sends the configuration without them, whose values are the pipeline's.
- `tests/service/test_rerun_review_signatures.py`: a lone surrogate escape over HTTP is the envelope refusal (400 E100,
  never E900), and the same payload in process is a signed INVALID_FORMALIZATION (E100).
- `tests/stem/test_e2e_run1_detection.py`: the rational-power step and its roots under the root-set rule
  (`docs/STEM_DESIGN.md`, section 24.10).
- `tests/channel/test_lens_round_d.py`: a syntheses-file field the format does not hold is refused, never dropped,
  relayed and refused by the hub or refused by the harness, as above.
- `scripts/arena/test_arena_rules.py`: the counterexample listing test uses a translation whose point is unlinked as a
  whole; a new test pins that the earlier fixture's counterexample over an unlinked conjunct is AMBIGUOUS_TRANSLATION,
  not released and not listed (B8).

## New tests

`tests/translate/test_summary_fit.py`, `tests/translate/test_provider_output_bound.py`,
`tests/channel/test_strict_mappings.py`, `tests/channel/test_stem_task_agents_b17.py`,
`tests/branches/test_accuracy_marks_linear.py`, `tests/adapters/test_linear_text_readers.py`,
`tests/adapters/test_whole_identifiers_sweep.py`, `tests/integrity/test_rerun_review_course_level.py`,
`tests/integrity/test_rerun_review_envelope_signature.py`; each has its positive case and a clean control.

## Verification

Measured once on the integrated tree (the integrated rows of `docs/ARGUMENT_DIAGNOSTICS.md`, section 6): the full suite gives 7119 passed and 45
deselected (the stress selection, not run), with no failure and no expected failure; every recorded arena round keeps
its functional count (r1 30/30, r1-adv 150/151, r2 to r6 46/46, r7 177/177); the development corpus names 44 of 44
defects with 57 of 57 controls clean; the hold-out corpus, run once, names 48 of 66 defects (9 caught but not named, 9
missed) with 55 of 68 controls clean (13 false alarms, 2 of them new against the base), where the base named 13 with 45
clean.

# Repair round 1 of the argument diagnosis

The verifier's review of the integrated tree (four lenses: the two corpora, the invariants, an adversarial review and a
re-run of the earlier reviews' findings and their variants) reported 66 issues. Each is fixed at its cause, for its
class, with a positive test and a clean control, except A-INF-LEAP, which is recorded as remaining work below, and the
hold-out acceptance rule (A-GATE), which the classes fixed here bring closer but do not meet (Verification). Every
change adds information, withholds a verification no check established, or removes a false finding on correct work by
reading the answer as it is written; no check was loosened and no status was upgraded. Scope: these results prove
properties of the encodings and of this code only; no live model provider was called, and nothing has been deployed.

The staged changes are against the branch tip `7991e8b`, which descends from `8a78efe` by progress commits to
`tests/README.md` only; that file is the tip's (A-BASE).

## Fixes

| Issues | Fix | Where |
| --- | --- | --- |
| A-REG-1, ADV-02 (a fitted law named a wrong formula) | ST-REF-001 drops pure coefficients only; a decimal, a figure in scientific notation or a value equal to a stated quantity is a fitted constant with a unit ("x = 2.0F", 2.0 cm per newton) | `stem/reference.py`, `stem/relations.py` |
| A-REG-2 (an item read as unaddressed) | a mark annotation ("[2 marks]") is no term of the request item it follows | `channel/bus.py` |
| A-STEM-WF, ADV-05 a and e (wrong formulas outside the reference) | 70 quantities and 94 booklet laws in the closed reference; ST-REF-002 (a law with the booklet law's variables that differs from it as a function); a result's dimension from its chain's last line and from the request; ST-DIM-001 between a law and its result | `stem/reference_data.py`, `stem/reference.py`, `stem/relations.py` |
| A-STEM-UE, ADV-04, ss1 variant (unit conversions) | ST-UNIT-003 traces numerals the request states with units and numerals already in SI; a unitless binding is dimensionless as written; a binding in grams or minutes fails its unit companion; the substitution tolerance is scaled with the computed value | `stem/relations.py`, `stem/checks.py` |
| A-STEM-CG (contradictory givens) | ST-GIVEN-002 for a given outside the enclosure of the value the working computes for it; ST-GIVEN-003 for a probability outside [0, 1] and for events treated as exclusive or independent against the request's joint figures | `stem/relations.py`, `named.py` |
| A-STEM-STEP, A-STEM-MW, ss11 variant | ST-STEP-001 takes its first step from the request's one equation and reads the gap after a dollar delimiter from the right character; a value binding ("x = 5.") is working for ST-WORK-001; a stated operation ("Dividing by x,") is an explicit step | `stem/relations.py` |
| A-STEM-EXT, A-STEM-RND, ADV-05 b to d, ADV-06 (range) | ST-RANGE-001 reads the model, the input and a series of years as section 24.11 of `docs/STEM_DESIGN.md` says, and a negated caveat is none; the prose number reader glues numbers by the right token's spacing, so a rounded p-value that reverses the decision is ST-ROUND-001; ST-SCOPE-002 tells objects apart by an ordinal | `stem/relations.py`, `stem/document.py`, `stem/reference_data.py` |
| A-FA-STEMPARSE, ss4 variant, ss12, sp4, sp8, ps13, ss4-hub (STEM readings) | condition items, binary literals and input words after a result cue; a spaced AND dot; space-grouped thousands beside a sign; a rounding labelled with the wrong precision fails; ", which is false" is no asserted comparison; a direction stated in scientific notation is checked; a simplification of the request's expression is no restatement | `stem/`, `branches/quant.py`, `channel/bus.py` |
| INV-6 (an incomplete solution set) | a root stated for a request to solve the equation claims the full set; bare values that continue a stated root are members ("x = 0, 2 or −2"), so a correct set in that form holds and a wrong or short one fails, and a step to such a set concludes the set (an existing false error on "… x² = 4, giving x = 0, 2 or −2" is gone); a set read in part, or a root the statement calls one of several, claims no full set | `stem/relations.py` |
| A-INF-EQ, A-INF-CIRC, A-INF-HG, ADV-11, ADV-13, fidelity-4 variant (argument family) | an equivocal term used in two senses (closed table); a paraphrase restating the point (shared roots, definitions, synonym groups); a counted sample generalised to all; a step hidden in a conjunction, an unmarked converse link or dichotomy shown at info, a converse chain; options that differ by a complementary pair are no false dilemma; E112 compares arithmetic normal forms | `engine/argument.py`, `engine/argument_cues.py`, `engine/runner.py`, `lexis.py` |
| ADV-06 (control cues) | a bare "control", "controlled" or "trial" is no control cue, and neither is a negated one or a comparison with another time | `engine/argument_cues.py`, `engine/argument.py` |
| A-INF-BARE | the History text parser keeps a sole judgement line as the answer, so a bare assertion is named; a sign-off stays a note | `adapters/history_specialist/parser.py` |
| A-EVD-UNCH, weakened task-setting refutation | EVD-SRC-005: a needed premise of a task-authority kind with no excerpt that the task material does not hold, a warning in every task; a figureless task premise that no task record holds is refuted again | `translate/diag_evidence.py`, `translate/grounding.py`, `named.py` |
| A-EVD-CHERRY, ADV-03, A-EVD-AUTH, ADV-12 (evidence cues) | periods "Y1 to Y2" and "since Y1" and dated values; a named or collective expert's verdict, and the History pack's "has shown"; source-bound requests in other words ("Using Text C", "Compare Sources C and D", "Based on the extract") | `translate/diag_evidence.py`, `adapters/history_specialist/structural.py` |
| ADV-01, fidelity-1 variant, ADV-09 (quotation grounding) | a quotation premise that restates the point needs an excerpt that states it (`content_in_excerpt`); an excerpt about another entity or quantity grounds nothing; a conjunction the excerpt states is its content | `translate/grounding.py`, `translate/contracts.py` |
| A-FA-QUOTERULE, A-FA-RANGE, A-FA-POOLED, A-FA-QNT (false alarms on correct evidence) | a rule the excerpt states as a conditional, a universal rule or a biconditional grounds its premise, a converse never; a dated change is no range; a mean's divisor and a figure the answer derives are no figures the excerpts must state; CORE-QNT-001 reads period anaphors, labelled and year-led points and the pair in the sentence before | `translate/stated_rules.py`, `translate/grounding.py`, `translate/assertion.py`, `translate/pipeline.py`, `branches/quant.py`, `branches/packs.py` |
| A-FA-MENTION, ADV-07 | a word quoted after a negating frame is a mention; a quoted connective is a mention only after a naming frame ("the connective") | `adapters/markdown.py` |
| ADV-10, ADV-14 (display) | every summary and display line is one line (`named.one_line`), and the model text a message interpolates has its forgery words written "[...]" (`named.model_text`) | `named.py`, `translate/outcome.py`, `engine/argument.py`, `translate/diag_*.py` |
| ADV-08 (timing) | derived runs are memoised, share one incremental solver and skip the re-validation of runs made only of the bound problem's premises and conclusion | `engine/argument.py` |
| INV-1, INV-2 (quadratic request parsing) | the scope reader computes its sentence cuts, parts and collapsed text once and matches label gaps on bounded windows | `channel/request_parser.py` |
| INV-3 (pooled precision) | each route states its own interval, so claims whose stated intervals do not meet still contradict (INT-CONFLICT-001) | `integrity/cross_check.py` |
| INV-4 (coverage probes) | a skipped or undecided probe with source-linked evidence withholds the verdict (E110 or E111, "undecided") | `engine/runner.py` |
| INV-5 (release) | `diagnosis_incomplete` is unresolved; an overflow keeps the blocking diagnostics | `translate/outcome.py`, `translate/diag_core.py` |
| cf-3 | INT-LEDGER-029 on the short status of the checks ("All checks passed.") and on a check result with the process's or a report's checks as its subject | `adapters/markdown.py`, `integrity/ledger.py` |
| cf-5 | a quotation credited by a name in the text's title or by its kind ("the newspaper", "the bread price table") | `adapters/sources.py` |
| correctness-2 | a receipt with an AMBIGUOUS_TRANSLATION or UNSUPPORTED claim is ACCEPTED_WITH_FINDINGS, never a clean ACCEPTED | `channel/bus.py` |
| security-3 | a request document resupplied with the same text under another author, title, locator scheme or provenance is refused (INT-REQ-002), as another text under its id is | `channel/bus.py` |
| security-5 | an absent memory budget reads as `None` only in a dump that writes every never-`None` field of the configuration, so every dump mode of a genuine result verifies | `engine/results.py` |
| rc-7, rc-8 | an answer in a one-key answer object is read as its text; an answer wrapped in quotation marks stays a quotation (so its quotation checks still run), a quotation wrapping two or more sentences is no bare assertion, and the History chronology proxy reads its sentences as the core pack does (HI-CHR-001 no longer pairs a cue with a date of the next sentence); a JSON report followed by more text is INT-REQ-009 | `channel/bus.py`, `translate/diag_argument.py`, `adapters/history_specialist/sentences.py`, `adapters/history_specialist/structural.py` |
| re-5 | a router forward that names no delivery is INT-HANDOFF-018 | `channel/bus.py` |
| cf-2 | a disclosed `conflicts` record is a field of the syntheses format and is relayed | `scripts/arena/run_arena.py`, `scripts/arena/list_claims.py` |
| ps11 | documentation: the STEM front end's linear time on 400,000 characters of list items (about 5 s) | `stem/README.md` |

## Tests rewritten to a stricter rule

Each docstring says why. No test was weakened, skipped or deleted.

- `tests/translate/test_overseer_round1.py`: a located excerpt must also state the point it is cited for; the placeholder
  meaning "the point" is now asserted refused as circular, with a failed `content_in_excerpt` check (ADV-01).
- `tests/stem/test_checks_no_false_errors.py`: space-grouped thousands beside a sign are read and checked where they were
  withheld (ST-PARSE-001); correct working still never fails, a wrong grouped value now fails, and a list of values set
  apart by spaces stays three numbers (ss12). `tests/channel/test_stem_channel.py` and the STEM corpus data
  (`tests/stem/data/corpus_items.py`, `stem_corpus.json`) move the magnification probe from "named unreadable" to
  "caught" (INT-SUBJ-001 on its `eq` check).
- `tests/engine/test_rerun_review_runner.py`: a spent bound with a source stating the free symbol now withholds the
  verdict (E111); new tests cover the E110 shape, an undecided probe and the control without source evidence (INV-4).
- `tests/engine/test_argument_diagnostics.py`: the derived-run test captures every decided run at its digest and also
  asserts that each derived problem passes the validator (ADV-08); the cue-table pins include the new tables and the
  narrowed control cues (ADV-06).
- `tests/channel/test_relay_history.py`: the router forward names the delivery it carries on; a forward that names none
  is INT-HANDOFF-018 (re-5), and the test still asserts that the forward adds no finding of its own.
- `tests/engine/test_rerun_review_provenance.py`: every dump mode of four configurations verifies, and a changed budget
  still reads as forged (security-5).
- Data pins (data changes, not weakening): `tests/contract/test_named_model.py` (EVD-SRC-005, ST-REF-002, ST-GIVEN-003),
  `tests/contract/test_lexis.py` (the root reader and its tables), `tests/translate/test_evidence_diagnostics.py` (the
  rule order with EVD-SRC-005).

## New tests

`tests/data/repair_round1_cases.json` (the review's 122 probe cases: 80 defects and 42 controls) with
`tests/case_scoring.py` and `tests/contract/test_repair_round1_cases.py`; `tests/engine/test_argument_rerun_repairs.py`,
`tests/stem/test_repair_round1_variants.py`, `tests/translate/test_repair_round1_grounding.py`,
`tests/translate/test_repair_round1_evidence.py`, `tests/translate/test_display_lines.py`,
`tests/channel/test_request_scope_linear.py`, `tests/channel/test_receipt_no_verdict.py`,
`tests/channel/test_resupplied_metadata.py`, `tests/channel/test_json_envelopes.py`,
`tests/channel/test_forward_reply_link.py`, `tests/channel/test_arena_conflicts.py`,
`tests/integrity/test_ledger_check_status.py`, `tests/integrity/test_pooled_precision_disjoint.py`,
`tests/adapters/test_credit_by_title.py` and additions to `tests/adapters/test_quotation_roles.py`; each has its positive
case and a clean control.

## Remaining work

- **A-GATE**: the hold-out corpus names 60 of 66 defects (91%; the rule asks for 95%) and flags 6 of 68 controls (the
  rule allows one). One of the six, a Mathematics rounding control, is a false alarm that the integrated tree did not
  raise; the hold-out is not read, so its cause is not traced here.
- **The branch has moved on**: the staged set is on `7991e8b`; the branch now also holds the integration protocol, the
  integration kit and the combinator sub-project (`28bca5c` and two later commits). A trial merge of the staged set with
  that tip conflicts in 12 files (21 hunks), which the next integration step resolves.
- **A-INF-LEAP**: ARG-LINK-001 (leap_in_logic, info) still records a writer's link on many correct answers. It is an
  info record, never an accusation and never a release reason of its own, but it is noise. Telling a sound "A, so B" step
  from a non sequitur needs knowledge of the subject that no closed table holds, and each lexical rule tried flagged
  correct answers, so none is added.

## Behaviour that became more conservative

- A receipt whose claims have no verdict a clean receipt could stand on (AMBIGUOUS_TRANSLATION, UNSUPPORTED) is
  ACCEPTED_WITH_FINDINGS (correctness-2; six arena receipts).
- A coverage probe that was skipped or left undecided withholds the verdict when a source states the symbols it concerns
  (INV-4: E110, E111 "undecided").
- An unfinished claim-layer diagnosis keeps the claim from release (INV-5).
- In Mathematics a root stated for a request to solve the equation claims the full solution set, so a lost root fails
  (INV-6).
- A report's copy of a request text must carry the request's metadata (security-3), a router forward must name the
  delivery it carries on (re-5, a warning) and a JSON report followed by more text is refused (rc-8).

## Found and fixed while measuring

- The first replay of the arena lost two functional records of r1-adv (150 to 148): the rc-7 repair had read an answer
  that is one string in double quotes as a JSON string, which took away the quotation marks of a whole-answer quotation
  and the check of the altered quotation in it. A double-quoted answer is now no envelope (it stays a quotation); the
  false bare assertion rc-7 reported is fixed at its cause instead (a quotation wrapping two or more sentences is no bare
  assertion), and the History chronology proxy now reads a wrapped answer's sentences as the core pack does. The
  replay was then made again from fresh copies, with the full suite and both corpora (below).
- The INV-6 repair's connective reading fired only on a LaTeX "\text{ so }" and claimed the full set on a "Solve" request
  even when the set's later members were bare values ("x = 0, 2 or −2"), a false error on correct work. The members are
  now read, a set read in part claims no full set, and a step to a listed set concludes the set (`stem/relations.py`;
  `tests/stem/test_repair_round1_variants.py`).

## Verification

Measured once on the staged tree (`docs/ARGUMENT_DIAGNOSTICS.md`, section 6): the full suite gives 7495 passed and 45
deselected (the stress selection, not run), with no failure and no expected failure; every recorded arena round keeps
its functional count (r1 30/30, r1-adv 150/151, r2 to r6 46/46, r7 177/177); the development corpus names 44 of 44
defects with 57 of 57 controls clean; the review's 122 probe cases are all named or clean; the hold-out corpus, run once,
names 60 of 66 defects (6 caught but not named, none missed) with 62 of 68 controls clean (6 false alarms, one of them new
against the integrated tree), where the integrated tree named 48 with 55 clean. The hold-out acceptance rule (95% named,
at most one control flagged) is not met. The argument stage costs about 7 ms of CPU per claim at the median (15.0 ms with
it, 7.9 ms without, over the 407 recorded development proposals), down from about 10 ms before this round.

# Repair round 2 of the argument diagnosis

The verifier's review of the repair round 1 tree (the same four lenses, and a second blind hold-out outside the gate)
reported 46 issues. Each is fixed at its cause, for its class, with a positive test and a clean control, except those
listed under remaining work. The second hold-out's cases were not read: its missed classes were reproduced on probes
written for this round in the shapes the review names. Every change adds information, withholds a verification no check
established, or removes a false finding on correct work by reading the answer as it is written; no check was loosened
and no status was upgraded. Scope: these results prove properties of the encodings and of this code only; no live
model provider was called, and nothing has been deployed.

The changes are staged against the same base tip, `7991e8b`. The branch has since moved on (the integration protocol,
kit and combinator commits and progress notes, to `42b27c3`); the staged set is not merged onto it here. A trial merge
of the staged tree with that tip conflicts in 12 files (22 hunks: the integration contract, the arena harness and its
README, the markdown, source, History and generic parsers, the core pack, the ledger and its README, and the service).

## Fixes

| Issues | Fix | Where |
| --- | --- | --- |
| FA-ROUND-MAI-REGRESSION, fidelity-1 variant | subject words are read without units and scale words, compounds and possessives split, and two figures in one unseparated clause belong to their own subjects; an excerpt about exports grounds no premise about imports | `translate/grounding.py` |
| FA-AUTH-ESS-FOLD-INVERTED, I2 | a fold below one is read with its bound mirrored ("more than halved", "fell threefold"), a repeated fold in both readings, "close to doubling" as an approach band, a negated figure as negated | `branches/quant.py` |
| I1, I3, FA-ARITH-ECON-CROSS-SENTENCE, FA-ALLDATA-GEO-SERIES | the worked view keeps a link after a bare figure and marks an equation decided only when every link is checked; a quoted equation is another report's; a per-cent change that restates the previous sentence's worked result is checked against it; a list between two years is the consecutive years' series when the counts match | `branches/packs.py`, `branches/quant.py` |
| FA-SUPPORTED-BM-DERIVED | the report's original response is read for the written calculation that derives a figure, and the calculation must give it | `translate/pipeline.py`, `translate/grounding.py` |
| ADV2-01 | a supplied text's content stems and folded vocabulary are computed once per text | `translate/diag_evidence.py`, `adapters/sources.py` |
| ADV2-02 | a rearrangement substituted with the task's values binds its symbols to the request's quantities | `stem/checks.py` |
| FA-IFF-CS-MENTION | a comparison after "condition", "test", "guard" is a named condition unless the words after it evaluate it | `stem/document.py` |
| MISS-CIRC-PARAPHRASE, ADV2-10 | a paraphrase that drops a name, a year or a pre-modifier restates its fact; a quantity change restates nothing; "most" from a sample is hasty | `engine/argument.py`, `engine/argument_cues.py` |
| MISS-EQUIV-BIO, MISS-EQUIV-PHYS, ADV2-09 | one symbol read in two senses across premises and their labels; cue forms by root; the closed table read on a bridge (ARG-EQ-002) | `engine/argument.py`, `engine/argument_cues.py` |
| MISS-EXTRAP-SUBSCRIPT, ADV2-08 | a law whose head carries a subscript digit is a law; a trend stepped in arithmetic past the data is evaluated | `stem/parser.py`, `stem/relations.py` |
| MISS-UNCH-RUBRIC-TEXT | an opening judgement paragraph rests on the sentences after it | `branches/generic_parser.py` |
| NAME-CHERRY-GENERIC | recoveries are rises; month periods and month values; a point with no period of its own read against the request's period and the data's latest year | `translate/diag_evidence.py` |
| NAME-LINK-NONDISCRIMINATING | ARG-LINK-001 stays a dependency record, documented as such; a causal link a stated control warrants gets none, a stated rule is ARG-LINK-002; a reasoned conclusion ("Since ..., ...") that restates earlier sentences is read as a conclusion from them in text as in a report, so text mode names what report mode names | `engine/argument.py`, `adapters/markdown.py`, `branches/generic_parser.py`, `adapters/history_specialist/parser.py` |
| ADV2-03 | circularity answers are kept by content, so the translator's check and the engine's share one computation; the per-claim caches of the evidence and grounding rules; the end-to-end cost is stated in section 6 of `docs/ARGUMENT_DIAGNOSTICS.md` | `engine/runner.py`, `translate/` |
| ADV2-04 | complementary options are read by root ("passed" and "failed", "converges" and "diverges") | `engine/argument.py` |
| ADV2-05 | a quotation that differs only in form (a lowered initial capital) is no `source_mismatch`; INT-REQ-010 still names the form | `translate/diag_evidence.py` |
| ADV2-06, ADV2-07, ADV2-12 | roundings in words, comparisons in symbols, target and condition statements are `rnd` checks; word equations are read as the formulas they spell; a time converted in brackets binds the law's variable | `stem/relations.py`, `stem/word_formulas.py`, `stem/nodes.py` |
| ADV2-11 | a task premise whose label spells the task sentence's notation in words is validated by that sentence | `translate/grounding.py` |
| combinator-faults-3-variant, combinator-faults-5-variant, combinator-faults-8-variant | the self-certification vocabulary reads status lines and checkers; showing verbs credit a quotation; a sign is read the same in every glyph | `adapters/markdown.py`, `adapters/sources.py`, `integrity/ledger.py` |
| formal-robustness-1 variant | exact arithmetic beyond `MAX_COEFFICIENT_DIGITS` is refused with E307 before it is compiled | `engine/policies.py`, `engine/runner.py` |
| fidelity-4 variant | E112 reads a restatement Z3 finds equivalent beyond the normal form; the translator refuses it as circular "in other terms" | `engine/runner.py`, `translate/pipeline.py` |
| NAME-E04A-NO-MISMATCH | EVD-SRC-006: a source credited with the opposite stance of what it states | `translate/diag_evidence.py`, `named.py` |
| I4 | the translation-records heading names translator 0.5.0 | `docs/integration-contract.md` |
| I5 | the arena harness serves a bare recorded id to the agent-qualified id of the same claim and agent, its problem naming the id the claim now carries | `scripts/arena/run_arena.py` |
| robustness-and-contracts-7-residual, empty-request-residual, combinator-faults-11-residual, security-2-label-dependence | a JSON-wrapped original response has an answer; a request with no visible character is REJECTED; a field error names the validator's message, not the value; a relayed report is a peer document by id, author or provenance | `channel/bus.py`, `translate/grounding.py` |
| history-bare-assertion-false-alarm | a judgement whose sentence quotes a supplied text cites its evidence | `translate/diag_argument.py`, the parsers |
| GEN-HOLDOUT2 (the missed classes, on the round's own probes) | units in symbolic working (a law on its own line; a bare result read in its prose unit; numbers a substitution introduces); magnification; the Lincoln index, a dilution and pressure in the closed reference; labelled and unlabelled objects (ST-SCOPE-002) and a given rebound against the request (ST-GIVEN-002); givens that cannot all hold (ST-GIVEN-004: uniform motion and free fall, two-set counts); a request's own model past its range and a dated trend in Mathematics; rounding against targets and the request's conditions, the value before the rounding read in the rounded value's unit; two's complement and Boolean chains; a bare recommendation and an empty evaluation; AC and DA through conjunction facts, reversed bridges and packed premises; a sample stated of a wider whole; an equivocal bridge; cherry-picking past the data's end | `stem/`, `engine/argument.py`, `translate/diag_argument.py`, `translate/diag_evidence.py`, `named.py` |
| verifier probes ya06, zx01 | premises that contradict each other are never refused as circular, so the engine names the contradiction; a refused self-certifying output keeps its E505 line | `engine/runner.py`, `translate/pipeline.py` |
| false alarms on the round's own probes | a task fact in other words, an abbreviation of a subject, a unit of several words, an item answered in notation, a change across sentences | `translate/grounding.py`, `translate/quantities.py`, `channel/bus.py`, `stem/hub_hooks.py`, `branches/quant.py` |

## Tests rewritten to a stricter rule

Each docstring or comment says why. No test was weakened, skipped or deleted.

- `tests/engine/test_argument_diagnostics.py`, `tests/engine/test_argument_rerun_repairs.py`,
  `tests/engine/test_rerun_review_runner.py`: a restatement beyond the normal form (a De Morgan form, "2·dt = 82",
  "dt + 1 = 42" for dt = 41) now carries E112 and ARG-CIRC-001 (fidelity-4 variant); the "derived value" control
  became a test of its own that asserts the circle.
- `tests/stem/test_boolean_parse.py`: a chain of equivalences is read link by link; a chain beyond 16 links and an
  expression outside the grammar are still refused.
- `tests/branches/test_core_equations_b25.py`: no INT-SUBJ-001 of any kind on its correct answers (before, only the STEM
  ones were excluded).
- `tests/branches/test_quant_si_reading.py`: a repeated fold is read right in both readings (the earlier pin listed it
  among the general reading's misreadings).
- Data pins (data changes, not weakening): `tests/contract/test_named_model.py` (ARG-LINK-002, EVD-SRC-006,
  ST-GIVEN-004), `tests/translate/test_evidence_diagnostics.py` (the report rule order with EVD-SRC-006),
  `tests/engine/test_argument_diagnostics.py` (the added cue tables).

## New tests

`tests/data/repair_round2_cases.json` (181 cases: the review's adversarial probes and the round's own, 92 defects and 89
controls, two of them pinned as known limits) with `tests/contract/test_repair_round2_cases.py`;
`tests/stem/test_repair_round2_stem.py`, `tests/stem/test_repair_round2_layouts.py`, `tests/stem/test_repair_round2_classes.py`,
`tests/engine/test_argument_repair_round2.py`, `tests/engine/test_argument_repair_round2_classes.py`,
`tests/engine/test_repair_round2_restatement.py`, `tests/engine/test_repair_round2_coefficients.py`,
`tests/translate/test_repair_round2_evidence.py`, `tests/translate/test_repair_round2_grounding.py`,
`tests/translate/test_repair_round2_readings.py`, `tests/translate/test_repair_round2_perf.py`,
`tests/branches/test_repair_round2_quant.py`, `tests/branches/test_repair_round2_packs.py`,
`tests/branches/test_repair_round2_generic.py`, `tests/channel/test_repair_round2_channel.py`,
`tests/adapters/test_repair_round2_self_certification.py`, `tests/integrity/test_repair_round2_credit.py`,
`tests/integrity/test_repair_round2_figures.py`, and two arena harness tests in `tests/e2e/test_arena_measures.py`; each
has its positive case and a clean control.

## Remaining work

- **The hold-out acceptance rule** (GATE-HOLDOUT) is met on this run (65 of 66 named, no control flagged; below), but
  the round's repairs were made from the review's descriptions of hold-out classes, so the run no longer measures the
  rules apart from them; the second blind hold-out (GEN-HOLDOUT2) was not run again, so how far the class fixes
  generalise to it is not measured.
- **CASE-LEAP-LL-SLOGAN-REPORT**: a hold-out case cites no supporting claims for its point in report mode; the case file
  is not edited, and ARG-BARE-001 deliberately yields to a section whose other claims offer reasons.
- **parser-safety-11-residual**: a 400,000-character list answer takes about 3.4 to 3.7 s on the STEM front end, not under
  2 s (the read stops at 512 statements, but the span finder and the segmenter still pass over every line).
- **ARG-LINK-001** stays a record on most controls: telling a sound "A, so B" from a non sequitur needs subject knowledge
  no closed table holds (f01b is caught by info records and the dependency rule, not named at warning).
- **Two pinned controls** of the round's probe cases: a lowered initial capital stays INT-REQ-010 with an unverified
  grounding, and an answer made only of the request's words stays INT-REQ-011.
- **The branch has moved on**: the staged set is on `7991e8b` and is not merged onto the branch's later commits here (a
  trial merge with `42b27c3` conflicts in 12 files, 22 hunks); the next integration step resolves them.

## Behaviour that became more conservative

- Exact arithmetic beyond 16,000 digits is refused (E307) before it is compiled.
- A restatement Z3 finds equivalent to the point is E112, no verdict, and the translator refuses it as circular.
- A raw answer's reasoned conclusion rests on the sentences it restates, so its unchecked facts and sources are graded
  as in a report (more warnings in text mode, never fewer).
- A request with no visible character is REJECTED.

## Found and fixed while measuring

- The first arena replay of the staged tree served the bare-id recordings to the qualified ids (I5), but each recorded
  problem still named the bare id, so the translator refused them ("problem request_id/claim_id do not match the claim
  being translated": 44 r7 records and run1's ess-e1b), a refusal made by the harness, not by the claims. The harness
  now serves such a recording with its problem naming the claim's current id (`fixture_for_claim`, with its test); a
  problem about another claim is still refused, and the replay now verifies those claims (what that changes in r7 and
  run1 is in section 6 of `docs/ARGUMENT_DIAGNOSTICS.md`). The suite and the arena replay were then run again on the
  staged tree; the corpora, which do not use the harness, were not.

## Verification

Measured on the staged tree (`docs/ARGUMENT_DIAGNOSTICS.md`, section 6): the full suite gives 8062 passed and 45
deselected (the stress selection, not run), with no failure, no skip and no expected failure; every recorded arena round
keeps its functional count (r1 30/30, r1-adv 150/151, r2 to r6 46/46, r7 177/177) and the run1 replay keeps 120 of 134,
now serving all 224 of its recorded translations (218 in round 1); the development corpus names 44 of 44 defects with 57
of 57 controls clean; the round's 181 probe cases are named or clean, two pinned as known limits; the hold-out corpus,
run once, names 65 of 66 defects (the one caught but not named is the hold-out case error) with 68 of 68 controls clean,
where repair round 1 named 60 with 62 clean, so the hold-out acceptance rule (95% named, at most one control flagged) is
met on this run. End to end, the development corpus takes about 1.6 times the CPU time of the tree before the argument
diagnosis (`22d6a5b`; section 6, Cost). The suite and the arena replay were run a second time after the harness fix
above; the corpora, which do not use the harness, were run once.

# Repair round 3 of the argument diagnosis

The review of the repair round 2 tree reported 35 items (corpus, invariants, adversarial and re-run lenses). Each fixed
item is fixed at its cause, for its whole class, with a positive test and a clean control in the files named
`test_repair_round3_*.py`; three items are left with their reasons (below). The table of all 35, with what changed and the
tests, is `docs/ARGUMENT_DIAGNOSTICS.md`, section 9. No version changes (rules `argdiag-1`, engine 0.5.0, policy
2026.10-v5, translator 0.5.0, contract 0.4: `src/epinoic_logic/version.py`); the named-code table gains ARG-NS-003 and
ST-STEP-003 (50 codes).

Scope: these results prove properties of the encodings and of this code only. No live model provider was called (every
translation in the corpora and the arena is a recorded proposal). Nothing has been deployed.

## Fixes

- **Argument structure**: an argument in one sentence ("A, so B") is translated with no supporting claim; a sentence that
  opens with a conclusion lead or a ground phrase pointing back ("With turnover that high, ...") rests on the sentence
  before it; an unbridged leap between two named things is ARG-NS-003; a report that links nothing gives a ranking
  judgement no reason (ARG-BARE-001).
- **Grounding**: the refutations of figureless task premises made before repair round 2 are restored (a reported view, a
  question, a task sentence whose words the premise rearranges, an "if" no record states), so no check is weakened; a
  quoted conjunction is stated conjunct by conjunct, each with its own polarity and its distinguishing word; an excerpt's
  figure belongs to its own quantity, entity and period ("before the change" is not "after it"); a figure after "compared
  with" and a bound stated as a target are read for their own subjects; a peer document id is normalised before it is
  tested.
- **Evidence**: a figure the answer works out, dates or takes from a record's rounded figure is no invented figure
  (`grounding.assignment_support`); a trend from a window before a reversal is cherry-picked; a link resting on located
  excerpts that state no link is an unchecked source.
- **Engine readings**: exhaustive options, a census and the duration of an effect are no fallacies; a control cue
  warrants only the link it bears on; a post hoc over dated Bool facts is a causal leap; a "rule" note on a label that
  records no rule keeps the missing link; a tautological point is vacuous, not circular.
- **STEM**: ST-STEP-003 (a rewrite that is no identity), givens against a definition law, a rounding before a comparison
  written with the symbol, missing working in Computer Science and for "Show that", a cancellation read as a division, a
  request's model outside its range in every subject, a percentage written once.
- **Channel and provenance**: the response gate reads only structured data (a carried finding is made again from the
  receipt's history) and never reads an undiagnosed claim as passed; a legacy signature attests no key id
  (`signature_form`; the verify-signature route answers `key_id_attested: false`).
- **Integrity and adapters**: one figure in two notations of grouped thousands is one figure; quotation credit by an
  organisation's name and a document kind; the History chronology reader is linear in the answer's length (a 300 KB
  answer took about 270 s and now about 20 s through the whole hub on a loaded host).

## Tests rewritten to a stricter rule

- `tests/contract/test_named_model.py`: the table pins ARG-NS-003 and ST-STEP-003 and the generic set includes ARG-NS-003
  (exact pins, one more row each).
- `tests/translate/test_argument_rules.py`: the claim rules tuple includes `unbridged_leap`.
- `tests/service/test_review_service_fixes.py` (`test_another_build_or_an_earlier_release_is_never_eligible_over_http`): a
  genuine record of release 0.3.0 now answers `{"valid": true, "key_id_attested": false, ...}` (it answered a bare
  `{"valid": true}`), and its release check names its key id as not attested; every other assertion is the earlier one.
- `tests/channel/test_round3_fixes.py` (`test_an_echo_of_the_request_never_supersedes_the_genuine_report_or_its_pool`): the
  genuine report links nothing, so its ranking judgement "The timing mattered most." is named ARG-BARE-001 on arrival and
  carried on the relay; the test asserts exactly that finding where it asserted an ACCEPTED relay; every other assertion is
  the earlier one.

## New tests

`tests/channel/test_repair_round3_gate.py`, `tests/translate/test_repair_round3_reports.py`,
`tests/translate/test_repair_round3_grounding.py`, `tests/translate/test_repair_round3_evidence.py`,
`tests/translate/test_repair_round3_cherry.py`, `tests/translate/test_repair_round3_peer_ids.py`,
`tests/engine/test_repair_round3_argument.py`, `tests/engine/test_repair_round3_signatures.py`,
`tests/service/test_repair_round3_signatures_http.py`, `tests/integrity/test_repair_round3_ledger.py`,
`tests/stem/test_repair_round3_stem.py` and `tests/adapters_history/test_repair_round3_chronology_scale.py`; each class has
its positive case and a clean control, in wording of its own, so the review's probe sets stay independent of the tests.

## Remaining work

- **ADV3-11** (a lowered initial capital fails grounding): left, since verifying it would change the quotation-form rule
  that earlier tests pin; the false alarm stays (INT-REQ-010, HI-SRC-001, an unverified grounding).
- **INV-4** (the B8 flags take a COUNTEREXAMPLE out of the gate's accuracy): left, since the end-to-end decision B13 pins
  that a correct answer whose counterexamples come from dropped links is delivered "not verified"; an attempt that counted
  those claims failed broke that pin and was reverted.
- **V3-H2-CONTROL-FALSE-ALARMS**: heuristic readings on clean answers (ST-UNDEC-001, ES-STR-001, HI-STR-001, INT-REQ-008,
  INT-REQ-004, CORE-QNT-001) are left: each is a non-defect heuristic the gate counts unresolved, never failed.
- **ADV3-13 a and b**: an equivocation outside the closed table with no sense cue and a circle through irregular word
  formation stay caught, not named.
- **V3-CASE-REPORT-NO-SUPPORTING**: hold-out cases with no supporting links are case faults in a read-only corpus.
- **INV-8 and ADV3-12**: the wall-clock bounds of the suite can fail on a loaded host (the bounds are kept), and the cost
  is measured below.
- **Two false alarms this round makes, found by measuring** (not fixed after the measurement, so the measured tree is the
  staged one; `docs/ARGUMENT_DIAGNOSTICS.md`, section 7): a task's either/or recorded as an "or" premise with the task's
  authority and no excerpt is refuted again by the restored INV-3 check, as on the base tip (one hold-out control
  flagged); and the declared-unit reading this round widened (`quantities._DECL_UNIT_RE`) reads "in A (m³/s)" as amperes,
  so a correct Geography answer's quoted discharge fails grounding with EVD-SRC-003 (one control of the review's
  supplementary hold-out, run after the measurement).

## Behaviour that became more conservative

- A figureless task premise is refuted again where it was refuted before repair round 2 (more evidence failures named).
- A link that rests on located excerpts stating no link is EVD-SRC-001; a "rule" note on a bare label keeps the missing
  link.
- A report that links nothing gets ARG-BARE-001 for a ranking judgement with no reason.
- A legacy-form signature is refused by a receiver that trusts by key id, and its key id is reported as not attested.

## Verification

Measured once on the staged tree (`docs/ARGUMENT_DIAGNOSTICS.md`, section 6), with no model provider called:

- **Suite**: 8249 passed and 45 deselected (the stress selection, not run), with no failure, no skip and no expected
  failure, in 434 s (one serial run).
- **Development corpus** (101 cases): 44 of 44 defects named, none caught without a name, none missed; 57 of 57 controls
  clean; 47 controls not releasable. On its 35 end-to-end cases the evidence rules raise 13 warnings outside the cases'
  scopes, where repair round 2 raised 45 (EVD-FIG-001 and EVD-LACK-001 are gone from them).
- **Hold-out corpus** (134 cases, run once, not used to change any rule): 65 of 66 defects named, 1 caught but not
  named (the hold-out case error), none missed; 67 of 68 controls clean, 1 flagged (the either/or above); 38 controls not
  releasable. The acceptance rule (95% named, at most one control flagged) is met.
- **Arena replays** on fresh copies: r1 30/30, r1-adv 150/151, r2 to r6 46/46 each, r7 177/177, run1 120/134, the
  functional counts of repair round 2. r1 to r7 give every record the same status and finding codes as round 2; in run1
  no receipt changes status and 15 records of maa-e1a and hi-e1a lose an INT-ARG-001 that carried a false EVD-FIG-001
  (worked figures and dates).
- **Cost**: about 1.7 times the CPU time of `22d6a5b` on the development corpus (two interleaved pairs on a loaded host;
  repair round 2 measured about 1.6).

After the measurement, only documentation changed (these numbers, sections 6, 7 and 9 of `docs/ARGUMENT_DIAGNOSTICS.md`
and this file); the timing pairs and the run of the review's 18 supplementary hold-out cases (7 defects named, 10
controls as in round 2, 1 control with the declared-unit false alarm above) were made after it and changed no code.

# Repair round 4 of the argument diagnosis

The review of the repair round 3 tree reported 40 items (corpus, invariants, adversarial and re-run lenses). Each fixed
item is fixed at its cause, for its whole class, with a positive test and a clean control in the files named
`test_repair_round4_*.py` (and `tests/branches/test_annotation_strip_linear.py`); the items left are listed below with
their reasons. The table of all 40, with what changed and the tests, is `docs/ARGUMENT_DIAGNOSTICS.md`, section 10. No
version changes (rules `argdiag-1`, engine 0.5.0, policy 2026.10-v5, translator 0.5.0, contract 0.4:
`src/epinoic_logic/version.py`); the named-code table is unchanged (50 codes), and the policy manifest gains
`max_forced_value_digits`.

Scope: these results prove properties of the encodings and of this code only. No live model provider was called (every
translation in the corpora and the arena is a recorded proposal). Nothing has been deployed.

## Fixes

- **Quotation roles in their task** (INV-Q1, INV-Q2, INV-D1, ADV4-03, ADV4-04): corrections and suggestions are read only
  in marking, feedback, correction, proofreading and editing tasks, set by the channel from the plan; in an analysis an
  altered quotation behind an arrow, a "Model:" label, an imperative or 'Not "x" but "y"' is checked and named, and the
  response gate withholds the answer; mention frames ("avoids", "could have used") are read in every task, and marking
  feedback's corrected forms ("becomes", "it should read") raise no quotation finding.
- **Grounding** (FA-TASK-EITHER-OR-REFUTED, ADV4-06, E2E-BI, E2E-CS, E2E-MAA, E2E-HI, rerun-fidelity-1,
  rerun-security-2): an either/or the task states, a task fact restated in other words, a conversion given in an
  instruction, and the count, total and mean of a stated list (a last item after "and" included) ground their premises;
  a count read off a quoted list and an indexed lookup over it need no stated positions; a premise cited only to a
  peer's report is unvalidated, not refuted; one sentence that states two quantities gives each its own figure, and a
  month's figure is no other month's; an author or provenance holding an agent word marks a peer's report.
- **Argument structure** (ADV4-07, ADV4-10, ADV4-13, E2E-CS-FALSE-BARE-ASSERTION): a sentence that only names two things
  does not bridge a leap between them (ARG-NS-003); a paragraph's one reasoned claim is material; a pronoun conclusion
  states its own reason; a check tip's "should" is no judgement.
- **Engine** (rerun-formal-robustness-1, rerun-fidelity-4, ADV4-08, E2E-CS-IDENTITY-PROOF-NAMED-VACUOUS): the values a
  nonlinear problem's products force are bounded before compiling (E307, `MAX_FORCED_VALUE_DIGITS`); a restatement split
  across premises is E112; one comparative after a relative clause, "light" as radiation and "did not work" for
  "ineffective" are named; a proof over no premise is an info record.
- **Release notes** (INFO-NAMED-DEFECTS-ON-CONTROLS): capped diagnostics are listed under their own line with no defect
  label, still blocking.
- **STEM** (ADV4-01, ADV4-02, ADV4-11, rerun-stem-soundness-12, rerun-stem-precision-11, rerun-parser-safety-13, ADV4-12):
  the absolute temperature, quantities already in SI, values the request gives, identities under any request, a line of
  arithmetic as an answer in every subject, space-grouped and scaled figures, chained trends read link by link, and
  CORE-SRC-007 for a figure a named data table states otherwise.
- **Integrity and adapters** (rerun-combinator-faults-3, -5, -7, -8, rerun-parser-safety-3): short self-certification,
  credit after a quotation, a paraphrased parallel trace and truth-table rows, one figure in two notations, a linear
  annotation stripper.
- **Cost** (ADV4-09): the answer's working is read once per text and the records' figures once per value, with identical
  results.

## Tests rewritten to a stricter rule

- `tests/adapters/test_quotation_roles.py`: the roles are read in a task; outside a feedback task every correction or
  suggestion frame leaves the span a quotation that is checked.
- `tests/contract/test_quotation_stub.py`: each text is read in its task, and the pinned role counts gain the mentions
  with their reason.
- `tests/contract/test_release_rules.py`: a capped diagnostic is listed under the capped line with its cap and no defect
  label (two assertions); it still blocks release.
- `tests/engine/test_rerun_review_runner.py` and `tests/engine/test_repair_round2_restatement.py`: two bounds of the
  writer's own that together restate the point ("dt ≤ 41" and "dt ≥ 41" for dt = 41) are a circle, E112, where they were a
  control; a new control keeps two premises that entail the point without restating it.
- `tests/engine/test_argument_diagnostics.py::test_the_cue_tables_are_pinned`: 17 synonym groups (16 before) and the
  "light" cues, the added data pinned exactly.

No test was weakened, skipped or removed.

## New tests

`tests/adapters/test_repair_round4_quotations.py`, `tests/branches/test_annotation_strip_linear.py`,
`tests/branches/test_repair_round4_materiality.py`, `tests/branches/test_repair_round4_mentions.py`,
`tests/branches/test_repair_round4_quant.py`, `tests/branches/test_repair_round4_table_figures.py`,
`tests/channel/test_repair_round4_answer_words.py`, `tests/engine/test_repair_round4_argument.py`,
`tests/engine/test_repair_round4_engine.py`, `tests/integrity/test_repair_round4_ledger.py`,
`tests/stem/test_repair_round4_stem.py`, `tests/translate/test_repair_round4_eligibility.py`,
`tests/translate/test_repair_round4_grounding.py`, `tests/translate/test_repair_round4_leap_bridge.py` and
`tests/translate/test_repair_round4_peer_labels.py`. Run on the repair round 3 tree, three of these files do not import
(they test functions this round adds) and 136 of the 246 cases of the other twelve fail; the cases that pass there are
the controls and a few shapes that already held, kept beside their new variants (the annotation reader's equivalence
cases, a conclusion with a named subject, a scale word against scientific notation that already compared). Five controls
fail on the round 3 tree as well: a task fact that gives the act to another agent (validated there, refuted now), a
correct area and a correct period over values the request gives (a false ST-UNDEC-002 there), and two changed figures in
notations that tree did not read.

## Remaining work

- **LEAP-NAMED-ONLY-BY-NONDISCRIMINATING-RECORD and the one-subject part of ADV4-07**: a leap about one named subject stays
  a record (ARG-LINK-001 at info, not releasable). 145 control links and 42 defect links of the development corpus and the
  review's adversarial sets have that shape, c01's sound "E. coli cells lack a membrane-bound nucleus, so E. coli is a
  prokaryote" among them, and a pinned control of ARG-NS-003 has it too: word overlap cannot tell the leap from the sound
  link (`docs/ARGUMENT_DIAGNOSTICS.md`, section 7).
- **ADV4-05** (a lowered initial capital fails grounding): left, pinned by the quotation-form rule of earlier rounds; an
  attempt that verified a writer-lowered excerpt flipped the round-2 pin and was reverted.
- **INV-B8** (an unlinked judgement is named only at info): left, pinned by the end-to-end decision B13; never released.
- **INV-T1**: the wall-clock tests can fail under load (13 did in the sharded runs, all pass alone); the bounds are kept.
- **CASE-LEAP-LL-SLOGAN-REPORT**: a hold-out case error in a read-only corpus.
- **FA-TASK-EITHER-OR-REFUTED, on the hold-out**: the either/or the task states is validated in the shapes the review
  described and in its probe of the control, but the measured hold-out control itself is still refuted (one control
  flagged, as in round 3). The hold-out was not read to find why, and nothing was changed after the measurement.

## Behaviour that became more conservative

- In a task that is not a marking, feedback or editing task, every quoted span behind a correction or suggestion frame is
  checked as a quotation (more quotation findings in analyses).
- A task fact restated with its act given to another agent is refuted (round 3 validated it).
- A restatement split across two premises of the writer's own is E112, no verdict.
- A nonlinear problem whose products force values beyond 2,000 digits is INVALID_FORMALIZATION (E307) before it compiles.
- A one-sentence argument with a pronoun conclusion is translated and diagnosed, and a paragraph's one reasoned claim is
  material, so a warning on it reaches the receipt (INT-ARG-001).
- A leap between two named things is named even when another sentence names both things.
- An identity the answer states is checked under any request; a time or a temperature substituted unconverted fails its
  unit check.

## Verification

Measured once on the staged tree (`docs/ARGUMENT_DIAGNOSTICS.md`, section 6), with no model provider called (a first run
was stopped at 13% of the suite, before any result, to add the regression tests above):

- **Suite**: 8565 passed and 45 deselected (the stress selection, not run), with no failure, no skip and no expected
  failure, in 403 s (one serial run).
- **Development corpus** (101 cases): 44 of 44 defects named, none caught without a name, none missed; 57 of 57 controls
  clean; 47 controls not releasable. On its 35 end-to-end cases the evidence rules raise no warning outside the cases'
  scopes (round 3 raised 13).
- **Hold-out corpus** (134 cases, run once, not used to change any rule): 65 of 66 defects named, 1 caught but not named
  (the hold-out case error), none missed; 67 of 68 controls clean, 1 flagged (the task either/or above); 38 controls not
  releasable. The acceptance rule (95% named, at most one control flagged) is met.
- **Arena replays** on fresh copies: r1 30/30, r1-adv 150/151, r2 to r6 46/46 each, r7 177/177, run1 120/134, the
  functional counts of round 3. r1 to r7 give every record the same status and finding codes as round 3; in run1 no
  receipt changes status, five hi-e1a records lose the INT-SUBJ-001 on a quoted line of another report (seven gain the
  CORE-QNT-001 that says it was not decided), and four cs-e1 records lose an INT-ARG-001 raised by a check tip and derived
  counts.
- **Cost**: about 1.6 times the CPU time of `22d6a5b` on the development corpus (two interleaved pairs after the
  measurement: 14.7 and 15.4 s against 23.6 and 24.1 s), where round 3 measured about 1.7 on a loaded host.

After the measurement, only documentation changed (these numbers, sections 6, 7 and 10 of `docs/ARGUMENT_DIAGNOSTICS.md`,
this file and the design documents); the timing pairs were made after it and changed no code.

# Repair round 5 of the argument diagnosis

The review of the repair round 4 tree reported 39 items (corpus, invariants, adversarial and re-run lenses). Each fixed
item is fixed at its cause, for its whole class, with a positive test and a clean control in the files named
`test_repair_round5_*.py`; each positive case was checked to fail on the tree before the round. The items left, or left
in part, are listed below with their reasons. The table of all 39, with what changed and the tests, is
`docs/ARGUMENT_DIAGNOSTICS.md`, section 11. No version changes (rules `argdiag-1`, engine 0.5.0, policy 2026.10-v5,
translator 0.5.0, contract 0.4: `src/epinoic_logic/version.py`); the named-code table keeps its 50 codes (ARG-CIRC-003 is
also made in the report layer).

Scope: these results prove properties of the encodings and of this code only. No live model provider was called (every
translation in the corpora and the arena is a recorded proposal). Nothing has been deployed.

Traceability: the measured tree is `7991e8b` (the verified line `22d6a5b`, the end-to-end fixes `0d28eba`, `dae3265` and
`8a78efe`, and eight progress notes) with the argument-diagnosis integration and its five repair rounds staged on top,
uncommitted.

## Fixes

- **Leaps and circles** (DA-1, ADV5-01, ADV5-15 c, ADV5-11): an unbridged leap of two more shapes is named (ARG-NS-003: a
  ranked cause the reason never mentions; an advised action toward a new named thing); the leap reader splits sentences in
  one linear pass; a claim whose reason clause only restates its point is ARG-CIRC-003 in the report layer; ARG-BARE-001
  reads only the labelled parts whose items ask for reasons.
- **Engine readings** (INV-LINK-1, ADV5-15 a and b): a figure relation is listed with the facts (ARG-FACT-001), never named
  the writer's leap with an empty consequent; cases named by a list or a label make a hasty generalisation; a causative
  verb with a result comparative reads a cause.
- **Grounding** (ADV5-02, ADV5-09, DA-2, DA-5, rerun-fidelity-1, rerun-fidelity-2, rerun-security-2): an excerpt whose
  clause contradicts the literal it is cited for refutes it; definitions and closed enumerations a record states are rules
  it states; only negation words negate a stated list; a parenthesised unit gloss is the declared unit ("in A" a label);
  list items, comma-cut qualifiers and table cells keep each quantity's own figure; a ratio encoded cross-multiplied is a
  precision site; "relay:", "rep-", AI authors and the router mark peer documents.
- **Quotations** (ADV5-08, INV-QROLE-1): mentions in more frames; a record's own task type never widens the quotation
  roles, and `check-report --task-type` states the operator's.
- **Ledger** (rerun-combinator-faults-3, -5, -7, -8, ADV5-12): swaps between parallel statements, ordinal step labels,
  accounting parentheses and precision notes, more status forms, more credit forms; a word count is never INT-LEDGER-029.
- **Channel** (rerun-robustness-and-contracts-7, -8): nested envelopes and envelope tags are unwrapped; a structured reply
  cut off in transit is refused (INT-REQ-009).
- **STEM** (ADV5-03 to ADV5-07, ADV5-10, ADV5-16, ADV5-18, rerun-stem-soundness-10): units given only in the request,
  inline givens, rounded conclusions, adjacent letters, rebound symbols, reasoned proofs, unit homographs, counts in
  sentences and '±' chains (`docs/STEM_DESIGN.md`, section 24.15).
- **Generic parser** (rerun-parser-safety-11): linear on answers made of list items or numbered parts.
- **Cost** (ADV5-13, in part): pure readers cached, a repeated consistency check of derived runs dropped, exact fast
  paths in the mark readers.
- **Documentation** (INV-DOC-1, DA-6): the contract's section 8 example is the CLI's output; the measured tree's base is
  stated.

## Tests rewritten or extended, each to a rule at least as strict

- `tests/translate/test_joined_quotation.py`: the negated literal whose excerpt states the atom is refuted (it was
  verified).
- `tests/contract/test_quotation_stub.py`: one more pinned mention ('the text never says "ayudar"'), with its reason;
  every other role unchanged and still pinned exactly.
- `tests/translate/test_argument_rules.py`: the report rules pinned exactly, with the added rule.
- `tests/engine/test_argument_diagnostics.py::test_the_cue_tables_are_pinned`: 18 synonym groups (17 before), the added
  group pinned exactly.

No test was weakened, skipped or removed.

## New tests

`tests/adapters/test_repair_round5_quotations.py`, `tests/branches/test_repair_round5_generic_lists.py`,
`tests/channel/test_repair_round5_channel.py`, `tests/engine/test_repair_round5_engine.py`,
`tests/integrity/test_repair_round5_ledger.py`, `tests/service/test_repair_round5_cli.py`,
`tests/stem/test_repair_round5_stem.py` and `tests/translate/test_repair_round5_translate.py`. Run on the repair round 4
tree, two of these files do not import (they test functions this round adds) and 60 of the 103 cases of the other six
fail; the cases that pass there are the controls, a shape that already held (a spaced "½ m v") and the equivalence cases
of the derived runs. On the staged tree all 163 cases of the eight files pass.

## Remaining work

- **ADV5-17** (a source figure encoded at its written precision is refused): left, three pinned tests state that a given
  figure with no cue states no interval; an attempt contradicted them and was reverted. A retry at the exact value passes.
- **ADV5-14** (a lowered initial capital fails grounding): left, pinned by the quotation-form rule of earlier rounds.
- **DA-3** (a report point whose evidence is never linked): left; the hold-out case and its paired control have the same
  structure, and a text reading would be tuned on a hold-out case. Not releasable, never shown as success.
- **DA-4** (info labels on clean answers): figure relations no longer carry the leap label; the interpretive-link record
  stays, by design and pinned.
- **ADV5-15 d** (affirming the consequent over a nonlinear condition): the linear policy refuses it (E201), so no
  pattern is named.
- **DA-5, the rest**: non-defect structure codes and info-only names on a corpus this round may not read.
- **ADV5-13, the rest**: the derived runs themselves (section 6 of `docs/ARGUMENT_DIAGNOSTICS.md` has the ratio).
- **DA-1, the one-subject shape**: still a record, as in round 4.
- **Three false alarms the measurement found** (this round's readings, on genuine answers of the arena replay and their
  planted variants; no receipt changes status; left as found, no code changed after the measurement;
  `docs/ARGUMENT_DIAGNOSTICS.md`, section 7): an excerpt of function words that the answer analyses as words ("it was
  the", "she") is refuted as a placeholder (r2 en-t4, r6 en-t11); a figure after a lead phrase ("Before the tax, a litre
  ... sold for $1.60 on average") is read as another quantity's (run1 ec-e1); a correct summary that skips an
  intermediate value is read as a swap, INT-LEDGER-023 (r1 hi-t1 synthesis).

## Behaviour that became more conservative

- An excerpt whose clause contradicts the literal it is cited for refutes it (GROUNDING:FAILED where it was verified).
- Outside the channel, a report's or a claim's own task type no longer widens the quotation roles: a correction frame in
  such a report is checked as a quotation unless the operator states the task.
- A structured reply cut off in transit is REJECTED (INT-REQ-009).
- A swap between parallel statements is charged INT-LEDGER-023 again when its telling word stands far before the figure.
- More status forms are INT-LEDGER-029; more credit forms are miscredits.
- A claim that only restates its point in its reason clause is named circular (report layer); a part that asks for
  reasons is read for bare assertions.

## Verification

Measured once on the staged tree (`docs/ARGUMENT_DIAGNOSTICS.md`, section 6), with no model provider called:

- **Suite**: 8728 passed and 45 deselected (the stress selection, not run), with no failure, no skip and no expected
  failure, in 426 s (one serial run).
- **Development corpus** (101 cases): 44 of 44 defects named, none caught without a name, none missed; 57 of 57 controls
  clean; 47 controls not releasable.
- **Hold-out corpus** (134 cases, run once, not used to change any rule): 65 of 66 defects named, 1 caught but not named
  (the hold-out case error), none missed; 68 of 68 controls clean (the psychology either/or flagged in rounds 3 and 4 is
  clean); 37 controls not releasable. The acceptance rule (95% named, at most one control flagged) is met.
- **Arena replays** on fresh copies: r1 30/30, r1-adv 150/151, r2 to r6 46/46 each, r7 177/177, run1 120/134, the
  functional counts of round 4; no receipt changes status. Two planted STEM faults gain a check; the three false alarms
  above appear on genuine answers.
- **Cost**: about 1.55 times the CPU time of `22d6a5b` on the development corpus (two interleaved pairs after the
  measurement: 14.15 and 14.09 s against 22.19 and 21.38 s), about 1.6 times on the largest end-to-end answers (the review
  measured 2 to 2.5 times there).

After the measurement, only documentation changed (these numbers, sections 6, 7 and 11 of `docs/ARGUMENT_DIAGNOSTICS.md`,
this file and the design documents); the timing pairs were made after it and changed no code.

# Close round 1 of the argument diagnosis

The regression review of the repair round 5 tree compared it with the committed base `7991e8b`, input by input, against
the correct outcome of each input, and found 16 items on which the staged tree was worse than the base (two of them
security items). Each is closed at its cause, so that the reading it came from fires, or stays silent, only inside the
class it was written for; no reading was reverted. Every closed item has a regression test with its correct outcome and a
clean control in the files named `test_close1_*.py`, in wording of their own; each positive case was checked to fail on
the tree before the round. The table of the 16 items is `docs/ARGUMENT_DIAGNOSTICS.md`, section 12; the review's GAP and
IMPROVED items, which the base fails the same way, are listed there in section 7 as known defects for round 8. No version
changes (rules `argdiag-1`, engine 0.5.0, policy 2026.10-v5, translator 0.5.0, contract 0.4); section 7 there gives the
reason.

Scope: these results prove properties of the encodings and of this code only. No live model provider was called (every
translation in the corpora and the arena is a recorded proposal). Nothing has been deployed.

Traceability: the measured tree is `7991e8b` with the argument-diagnosis integration, its five repair rounds and close
round 1 staged on top, uncommitted.

## Fixes

- **Stated rules** (ADV6-01, ADV6-09): a source rule the excerpt states only hedged or in another mood, with an "or" in
  its consequence, with a part of its condition the premise drops, framed or denied, as a question, limited by an opening
  phrase, restricted after it or credited to someone's view is not the source's own statement: its excerpt refutes the
  premise that encodes it plainly (`source_mismatch`), and a record sentence of it validates no task rule; the month
  "May" is no modal.
- **Task facts** (INV7-1): a task sentence of another time, another tense or the opposite direction of change does not
  state a premise, and refutes it when it states the conflict.
- **Excerpts and figures** (arena r2 en-t4, r6 en-t11, run1 ec-e1): an excerpt of the words a literal quotes or names is
  no placeholder; another figure of the same value, or a figure of the opposite part, is no other figure for a premise's
  quantity.
- **Quotations** (rerun-verify6-weakened-negated-quotation-mention): the negated-verb mention frame takes one quoted word
  only, and a credit to a source after a span keeps it a quotation.
- **Self-certification, security** (ADV6-08, rerun-verify6-parser-safety-3-regression-selfcert): `SELF_CERT_RE` reads the
  same forms in linear time; a timing test pins it.
- **Ledger** (arena r1 hi-t1 synthesis): a figure kept with the source's own words after it is no swap.
- **Circles** (arena r7 lit-t13): a claim that only restates the task under the task's authority, with no reason, is an
  info record of ARG-CIRC-001; the refusal stands.
- **STEM** (ADV6-02, ADV6-07): a magnitude after its own signed chain is no restatement error; a rate, a step or a result
  in prose is no evaluation point of a model (`docs/STEM_DESIGN.md`, section 24.16).
- **Rule text** (V6-DA-05): the examples of the leap reader are written for the rule; no hold-out-only name is left in the
  source.

## Tests

New: `tests/adapters/test_close1_quotation_roles.py`, `tests/adapters/test_close1_selfcert_linear.py`,
`tests/integrity/test_close1_ledger.py`, `tests/stem/test_close1_stem.py`, `tests/translate/test_close1_circular.py`,
`tests/translate/test_close1_grounding_words.py`, `tests/translate/test_close1_rule_examples.py`,
`tests/translate/test_close1_stated_rules.py` and `tests/translate/test_close1_task_facts.py`. No existing test was
rewritten, weakened, skipped or removed: none pinned a regressed behaviour.

## Given up, and left

- **ADV6-07, in part**: an evaluation point written as an attribute ("a 40 N load ...") is no longer read; the hold-out
  case `ho_d_extrap_phys` is caught but no longer named, its verdict on the base.
- **ADV6-02, in part**: a prose value of the other sign than its own statement's chain is not checked, so a wrong
  magnitude or a dropped sign in that statement goes unchecked, as on the base.
- **arena r7 lit-t13, in part**: a circle whose premises and point all claim the task's authority, in a claim with no
  reason, is recorded at info rather than named at warning (the refusal stands; the base names no circle there).
- **Whitespace runs in other self-certification patterns** (found while closing ADV6-08; on the base at the same cost):
  quadratic at one anchor, left for round 8 with their own timing test.
- **Known defects**: the review's GAP and IMPROVED items, each failing on the base the same way
  (`docs/ARGUMENT_DIAGNOSTICS.md`, section 7).

## Behaviour that became more conservative

- A hedged, framed, restricted or cut source rule refutes the premise that encodes it plainly (GROUNDING:FAILED where it
  was verified).
- A task sentence of another time, tense or direction of change refutes the premise it seemed to state.
- A span of more than one word after a negated verb is checked as a quotation.

## Verification

Measured once on a fresh copy of the staged tree (`docs/ARGUMENT_DIAGNOSTICS.md`, section 12), with no model provider
called:

- **Suite**: 8847 passed, 1 failed and 45 deselected (the stress selection, not run) in 457 s, one serial run; the failure
  is the wall-clock bound of `tests/engine/test_stem_shapes.py::test_median_time_per_shape_is_below_50_ms` on a loaded
  host (51.6 ms against 50 ms), which passed three times of three when run alone on the same copy. The bound is not
  relaxed.
- **Development corpus** (101 cases): 44 of 44 defects named, 57 of 57 controls clean; no case worse than on the base.
- **Hold-out corpus** (134 cases, run once, not used to change any rule): 64 of 66 defects named, 2 caught but not named,
  none missed; 68 of 68 controls clean; no case worse than on the base.
- **Arena replays** on fresh copies: the functional counts of the base in every round (r1 30/30, r1-adv 150/151, r2 to r6
  46/46, r7 177/177, run1 120/134); no difference from the base that repair round 5 did not already have, the review's
  regression records back to the base's outcome, no planted fault lost.
- **Repros** of all 16 items on the fresh copy and on the base: the base's outcome or a stricter one.
- **Cost**: `SELF_CERT_RE` is linear (2.0 to 2.7 times the base pattern's cost on long whitespace runs); a History answer
  with a 20,000-space run is received in 0.41 s (the base 55 s).

After the measurement, only documentation changed (sections 7 and 12 of `docs/ARGUMENT_DIAGNOSTICS.md` and this file).

# Close round 2 of the argument diagnosis

The regression review of the close round 1 tree compared it with the committed base `7991e8b`, input by input, against the
correct outcome of each input, and found 9 items on which the staged tree was worse than the base (one a security item).
This round works under a convergence rule: a reading that close round 1 had already narrowed, or that would need a second
narrowing, is not narrowed again; its effect is reverted to the base's reading for its whole class, its regression test
keeps the base's outcome, and the improvement given up is recorded. A reading no close round had touched is narrowed only
by a plain restriction, never by a new reading; the security item is made linear with a timing test. The table of the 9
items is `docs/ARGUMENT_DIAGNOSTICS.md`, section 13; what is left, given up and still known to fail is in section 7 there.
No version changes (rules `argdiag-1`, engine 0.5.0, policy 2026.10-v5, translator 0.5.0, contract 0.4); section 7 there
gives the reason.

Scope: these results prove properties of the encodings and of this code only. No live model provider was called (every
translation in the corpora and the arena is a recorded proposal). Nothing has been deployed.

Traceability: the measured tree is `7991e8b` with the argument-diagnosis integration, its five repair rounds and close
rounds 1 and 2 staged on top, uncommitted.

## Fixes

- **Quotation roles, security** (SEC-QROLE-QUADRATIC): the role reader is linear in the text (line starts, sentence marks
  and label heads read once, the last correction remembered, possessive gap patterns, one reading per answer); the roles
  are the old reader's. A timing test pins it.
- **Quotations after a contrast** (DIFF-02, reverted): a span after "unlike", "rather than" or "instead of" is a quotation
  and is checked, as on the base; "without", "with no" and "no" keep their mentions.
- **A proposition the task quotes for discussion** (REG-CIRC-TASK-PROPOSITION, reverted): a task premise that shares an
  atom with the point is never validated by a task sentence, so "'X.' Discuss." no longer grounds 'X, as the question
  states; therefore X': the circle is named (E112), as on the base.
- **The AND dot and Boolean constants** (DIFF-04, narrowed): an answer that writes a Boolean constant with the AND dot
  ("A.0") is read without the AND dot, as on the base, so a wrong step written that way is charged again
  (`docs/STEM_DESIGN.md`, section 24.17).
- **A count's open precision** (DIFF-06, narrowed): "about 300" for a count is read at its first significant digit,
  whether the count is compared over Int or over `to_real`; a ratio keeps both readings.
- **Relay history on syntheses** (DIFF-05, narrowed in part): a synthesis carries no finding about its source reports'
  paragraphs or sentence style (ES-STR-, ES-STY-, HI-STR-); the history it references keeps them.

## Tests

New: `tests/adapters/test_close2_quotation_roles.py`, `tests/channel/test_close2_synthesis_layout.py`,
`tests/stem/test_close2_boolean_dot.py`, `tests/translate/test_close2_precision_counts.py` and
`tests/translate/test_close2_task_proposition.py`. Rewritten to the stricter base behaviour, and said so in the file and in
section 11 of `docs/ARGUMENT_DIAGNOSTICS.md`: the "unlike" case of `tests/adapters/test_repair_round5_quotations.py` (both
spans are quotations, where it pinned a mention). No test was weakened, skipped or removed.

## Given up, and left

- **Given up by the reverts**: a short word set aside by a contrast as one the text does not use is checked again and can
  raise INT-REQ-003 on correct work, as on the base (DIFF-02); a figureless task fact that the point restates is no longer
  a transcription the task validates and is left to the circularity rules, as on the base (REG-CIRC-TASK-PROPOSITION).
- **Given up by the narrowings**: a correct step written with a Boolean constant and the AND dot is charged as on the base
  (DIFF-04); a synthesis no longer carries a layout finding that is true of its source report (DIFF-05).
- **Left**: DIFF-01 (a plainly stated source rule with a qualifier word elsewhere in its sentence is still refuted: close
  round 1's reading, which may not be narrowed again, and whose revert would reopen ADV6-01); DIFF-03 (an excerpt that
  negates a rule's consequence leaves the premise unvalidated, not named; naming it needs a new reading); DIFF-07 (the
  hold-out leap after "since its" is named at info only; the base's flag was a false CORE-QNT-001); the rest of DIFF-05
  (relays and one synthesis carry findings their source receipts raise falsely in both trees). The reasons are in section 7
  of `docs/ARGUMENT_DIAGNOSTICS.md`.

## Behaviour that became more conservative

- A span after a contrast is checked as a quotation.
- A task premise that restates the point, with no figure, is no longer validated by the task: the circularity rules decide.
- An answer that writes a Boolean constant with the AND dot is checked as on the base.

## Verification

Measured once on a fresh copy of the staged tree (`docs/ARGUMENT_DIAGNOSTICS.md`, section 13), with no model provider
called:

- **Suite**: 8912 passed and 45 deselected (the stress selection, not run) in 453 s, one serial run, no failure.
- **Development corpus** (101 cases): 44 of 44 defects named, 57 of 57 controls clean; every verdict is close round 1's; no
  case worse than on the base.
- **Hold-out corpus** (134 cases, run once, not used to change any rule): 64 of 66 defects named, 2 caught but not named,
  none missed; 68 of 68 controls clean; every verdict is close round 1's; no case worse than on the base.
- **Arena replays** on fresh copies: the functional counts of the base in every round (r1 30/30, r1-adv 150/151, r2 to r6
  46/46, r7 177/177, run1 120/134), no planted fault lost; the round adds no difference from the base and removes 12 (the
  layout carries on syntheses); the genuine-answer findings the base does not raise are close round 1's 9 improvements.
- **Repros** of the 9 items on the fresh copy and on the base: the closed and reverted items give the base's outcome or a
  stricter one; the left items give what section 7 there records.
- **Cost**: the quotation-role reader is linear (32,000 spans on one line read in 3.4 s, where the review measured 25.7 s);
  the English feedback answer of 189,000 characters takes 7.7 s of CPU through the hub (the base 4.7 s; 46 s before the
  round); the review's quotation shapes are at most 1.9 times the base.

After the fresh copy was taken, only documentation changed, with one comment of `adapters/markdown.py` and the docstring
of one test of this round.

# Close round 3 of the argument diagnosis

The regression review of the close round 2 tree compared it with the committed base `7991e8b`, input by input, against the
correct outcome of each input, and found 10 items on which the staged tree was worse than the base (two of them security
items). This round works under close round 2's convergence rule (a reading an earlier close round narrowed, or that would
need a second narrowing, is not narrowed again: its effect is reverted to the base's reading for its whole class; a reading
no close round had touched is narrowed only by a plain restriction; a security item is made linear with a timing test) and
under a discrimination rule: a base outcome counts as a detection only when the base tells the defective input from its
matched correct control. Where the base flags the two alike, the staged tree's miss is a known gap, listed with the control
evidence and not fixed; a false alarm on correct work that the base does not raise is still a regression. The table of the
10 items is `docs/ARGUMENT_DIAGNOSTICS.md`, section 14; what is left, given up and still known to fail is in section 7
there.

Versions: the translator moves to 0.5.1 and the argument rules to `argdiag-2` (`src/epinoic_logic/version.py`), so a
translation record or a diagnosed result of an earlier round of this release no longer reads as current (the rules had
changed under unchanged stamps since the release's first round). Engine 0.5.0, policy 2026.10-v5, IR 1.0 and contract 0.4
stay: no compilation, procedure, limit, allowlist or eligibility rule changed.

Scope: these results prove properties of the encodings and of this code only. No live model provider was called (every
translation in the corpora and the arena is a recorded proposal). Nothing has been deployed.

Traceability: the measured tree is `7991e8b` with the argument-diagnosis integration, its five repair rounds and close
rounds 1 to 3 staged on top, uncommitted.

## Fixes

- **Quotations after a negated reporting verb** (INV-QR-1, reverted): 'not only writes "..."', 'does not just say "..."'
  and every other span right after a negated reporting verb is a quotation and is checked, as on the base, so an invented
  quotation put there is named again; a negated report with words before the span ('It does not say that the plan has
  "failed"') keeps its mention.
- **A supposition the task sets** (DV2-04, narrowed): EVD-SRC-001 no longer names a task-authority premise that restates
  a supposition the task sets ("Assume that X.", "Suppose X."); the premise stays unvalidated, so release is still refused
  on it, as on the base.
- **Ledger cost, security** (DV2-06): the synthesis ledger's swap reader and figure index are linear in the two texts and
  give the old answers (a differential check over every arena round's ledger inputs and hostile variants); a timing test
  pins it. The review's hostile answers now take at most 1.2 times the base's time.
- **Repeated joint checks, security** (DV2-07, in part): a definitive cross-report consistency result is kept per
  identical problem, configuration, limits and signing key, so a channel no longer decides the same joint problem again on
  every later transmission; an undecided result is decided again. The findings are unchanged; the r7 round takes 2.4 to
  2.6 times the base's time, where it took 3.1.

## Tests

New: `tests/adapters/test_close3_quotation_roles.py`, `tests/translate/test_close3_task_suppositions.py`,
`tests/integrity/test_close3_ledger_linear.py` and `tests/integrity/test_close3_joint_memo.py`. Rewritten to the stricter
base behaviour, and said so in each file and in section 11 of `docs/ARGUMENT_DIAGNOSTICS.md`: the "never writes" cases of
`tests/adapters/test_repair_round5_quotations.py` and `tests/adapters/test_close1_quotation_roles.py`, and the "ayudar"
role of `tests/contract/test_quotation_stub.py` (each span is a quotation and is checked, where they pinned a mention).
The exact version pins moved with the versions (`argdiag-2`, translator 0.5.1) and stay exact. No test was weakened,
skipped or removed.

## Given up, and left

- **Given up by the revert** (INV-QR-1): a word the writer says the text never uses, written right after a negated
  reporting verb ('never once says "I love you"', 'never writes "roared"'), is checked again and can be named an invented
  quotation on correct work, as on the base.
- **Known defects** (the discrimination rule; the base flags each defect and its matched control alike): DV2-01 (a task
  sentence that reports a forecast, hope, plan or estimate validates a premise that states it as fact), DV2-02 (a
  title-case "May" in a headline read as the month) and DV2-09 (an excerpt that negates a rule's consequence named only at
  info).
- **Left**: DV2-03 (a plain source rule with a qualifier word elsewhere in its sentence is still refuted), DV2-05 (relays
  and syntheses carry findings their source receipts raise falsely in both trees) and DV2-08 ("about 300 g" for 260 g over
  Real is AMBIGUOUS_TRANSLATION): each reading was narrowed by an earlier close round, and a trial revert of it makes
  tests fail that pin true detections (17, 20 and 5 of them), which may not be weakened; and the remaining cost of one r7
  answer group (DV2-07: 11 to 12 times the base, the verification of claims the base's parser never serves). The reasons
  and the trial evidence are in section 7 of `docs/ARGUMENT_DIAGNOSTICS.md`; each needs a decision outside this round.

## Behaviour that became more conservative

- A span right after a negated reporting verb is checked as a quotation.

## Verification

Measured once on a fresh copy of the staged tree (`docs/ARGUMENT_DIAGNOSTICS.md`, section 14), with no model provider
called:

- **Suite**: 8946 passed and 45 deselected (the stress selection, not run) in 443 s, one serial run, no failure.
- **Development corpus** (101 cases): 44 of 44 defects named, 57 of 57 controls clean; every verdict and releasability is
  close round 2's; no case worse than on the base.
- **Hold-out corpus** (134 cases, run once, not used to change any rule): 64 of 66 defects named, 2 caught but not named,
  none missed; 68 of 68 controls clean; every verdict and releasability is close round 2's; no case worse than on the base.
- **Arena replays** on fresh copies: the functional counts of the base in every round (r1 30/30, r1-adv 150/151, r2 to r6
  46/46, r7 177/177, run1 120/134), no planted fault lost; every record is close round 2's (no finding, status, display or
  release differs); the genuine-answer findings the base does not raise are close round 2's 9 improvements.
- **Repros** of the 10 items on the fresh copy and on the base: the closed and reverted items give the base's outcome or a
  stricter one; the left and known-defect items give what section 7 there records.
- **Cost**: the review's hostile ledger answers take at most 1.2 times the base's CPU (rd_space_digits_physics 0.98 s at
  36,000 characters, the base 1.28 s; the review measured 3.97 s); the r7 round 2.4 to 2.6 times the base's time.

After the fresh copy was taken, only documentation changed.
