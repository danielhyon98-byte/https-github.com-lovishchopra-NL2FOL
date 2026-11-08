# Bug testing and stress testing: results

This file reports how the translator infrastructure is tested and what the tests have
found so far. The infrastructure is code, not an agent. It converts the English outputs of
specialist sub-agents into logical code (an IR the Z3 engine decides) so that no
miscommunication passes between the router, the subject specialists and the combinator.

Every figure below was measured on the code at the commit named. This file is updated after
each round. Last update: after the round-4 fix round (commit `a2d874d`), with the round-5
overseer verdicts that had arrived.

Paths: since architecture step 2 of phase 2 the Overseer is the sub-project `overseer/` (package `epinoic_overseer`), so
the overseer's tests named below as `tests/overseer/...` are `overseer/tests/overseer_tests/...`, `scripts/overseer/` is
`overseer/scripts/` and `src/epinoic_logic/overseer/` is `overseer/src/epinoic_overseer/`. `python -m pytest -q` at the
repository root runs the translator's suite (`tests/`), the overseer's (`overseer/tests/`) and, since architecture step
2c, the flash router's (`flash-router/tests/`).

## Which model runs which role

Deployment is kept as cheap as possible; checking during testing is done by the strongest
model.

- **Deployed agents run on the smallest, cheapest model tier.** This covers the subject
  specialists (configured only from their knowledge documents), the combinator, the
  translation provider and the logic-checking overseer agents. The test environment uses
  the same tier for each of these roles, so the results show how the deployed system
  behaves.
- **The checks every transfer depends on use no model at all.** The translator turns each
  output into IR, and the Z3 engine decides it. The engine results are signed, and they
  are the only results the router and the overseers trust. Each transfer takes
  milliseconds (see the stress tables below).
- **The strongest model tier does the checking in testing.** That tier runs the arena
  overseers and the judges of the overseer agents, plus the fixers. They check every output
  the cheap agents produce against what the translator delivered and against the engine's
  verdicts. That is, they confirm the logic recorded for each output is true to what the
  agent actually wrote.

## How the infrastructure is tested

Testing has three layers. A change is committed only when the first layer is green and the
harness rates of the second layer have not dropped.

1. **Automated suite.** 1,079 tests: 1,067 run by default, plus 12 stress-marked tests.
   Run them from the repository root:

   ```
   python -m pytest -q            # default suite, about 20 s
   python -m pytest -q -m stress  # stress-marked tests, about 2 min
   ```

   | Package | Tests |
   | --- | --- |
   | adapters (English, generic, shared parsing rules) | 288 |
   | translate (grounding, eligibility, pipeline, providers) | 176 |
   | branches (subject packs, arithmetic and chronology checks) | 179 |
   | integrity (envelopes, hand-off, ledger, cross-agent consistency) | 128 |
   | channel (requests, responses, relays, receipts) | 98 |
   | service (HTTP service, limits, signing) | 73 |
   | engine (validator, compiler, procedures) | 47 |
   | adapters_history (History parser and structural checks) | 45 |
   | e2e (end to end through the hub) | 34 |
   | stress | 11 |

   Thirty-three of the test files are regression files added by overseer rounds
   (`test_overseer_round*.py`, `test_round*_*.py`, `test_r*_*.py`). Each blocker or major
   finding that was fixed has at least one test that reproduces it.

   Wall-clock bounds ("this answer crosses the hub in under 2 s") are measured under the fixed
   conditions of `tests/timing.py`, never relaxed: a warm-up run, then the median of up to five
   runs, each a first crossing (the package's memoisation caches emptied) with the heap the earlier
   tests left behind frozen, and process CPU time recorded beside wall-clock time so a contended
   machine can be told from a slow path. `tests/test_timing.py` checks those conditions. The
   arena harness's separate measures (transport, fixture coverage, translation fidelity and claim
   counts) are tested in `tests/e2e/test_arena_measures.py`; its counting rules are in
   `scripts/arena/test_arena_rules.py`, which the default suite does not collect
   (`python -m pytest -q scripts/arena/test_arena_rules.py`).

   The two sub-projects have suites of their own, which the default suite runs and requires to pass:
   `flash-router/tests/` (`tests/integration/test_flash_router_subproject.py`) and `combinator/tests/`
   (`tests/integration/test_combinator_subproject.py`, which also shows that a faithful synthesis of the combinator passes
   the hub and that the hub names each misrepresentation it lets out: a dropped qualifier, a stronger certainty, a merged
   contradiction of formalized claims, an invented figure, a wrong attribution, a carried self-certification, a
   verification label, a self-certification of the synthesis itself, a note carried back as a claim, a figure in another
   unit or era, a dropped bound or frequency, a credit to both specialists for one specialist's claim, and an invented
   conflict, INT-CONFLICT-006 for information; `tests/integrity/test_synthesis_round3_readers.py` pins the readers behind
   them). Run one alone from its directory
   (`cd combinator && python -m pytest -q`), or install it into a separate environment (`pip install -e "combinator[dev]"`).

   The external review of 12 October 2026 is covered by `tests/engine/test_review_engine_fixes.py`,
   `tests/service/test_review_service_fixes.py`, `tests/translate/test_review_2026_10_12_translate.py`
   and `tests/channel/test_task_record_through_the_channel.py`: each of its nine findings has
   regression tests with negative controls in which the rejected conclusion really is wrong, and
   genuine signed results of earlier releases (`tests/engine/data/`) test the upgrade path.
   `tests/translate/test_quantities_linear_time.py` holds the figure reader the fixes added to
   linear time on long untrusted texts, and `tests/e2e/test_arena_measures.py` counts the claims
   whose release assessment permits release apart from the approvals. Finding 6 as repaired after
   the independent verification is in `tests/translate/test_coverage_assertion.py`: whether a
   source asserts a figure is read from its grammar (the verifier's paraphrases, a condition, a
   question, a possibility, a biconditional, a negation, "for any y", keep their counterexample;
   paired sources that do assert the figure are still no verdict), what a figure states must
   establish the encoding's comparison, a figure that counts something else is no evidence, the
   retry an E110 asks for may add only what the source asserts, and the reader stays linear.

   The second verification left findings 2 and 6 open; their repairs are tested at the cause, for
   the whole class. `tests/translate/test_whole_content_authority.py` (finding 2): a check confers
   task or source authority only on a premise's whole content, so a relation whose figures all
   occur in the task or in a located excerpt (`speed = d / 8` from "120 km in 8 hours") stays an
   unverified dependency and blocks release whatever its grounding label, while the same relation
   stated in the task as a given is validated (`relation_in_source`) and an assignment is validated
   only by a figure stated so that it establishes the comparison; negative controls cover a
   formula in a question, a claim to prove, a condition, a negation, a report or a hypothesis, and
   a rule given only in words; a located excerpt is read where it stands in its document, every
   reference's span counting and an elided excerpt's span only for what it quotes.
   `tests/translate/test_positive_assertion_reader.py`
   (finding 6): a sentence asserts a figure only when the reader positively recognises it as the
   writer's own statement, so every phrasing the verifier listed (hedges, hypotheses, reported
   speech, claims to test, quantified and symbolic conditionals and biconditionals, Unicode arrows
   included) keeps W110/W111 advisory and the valid counterexample, while plain statements, given
   frames, factual subordinate clauses and raising verbs of fact ("n turned out to be 17", against
   "n seems to be 17" and "n is believed to be 17") are still asserted (the paired E110/E111
   controls); the
   unchanged timing tests of `tests/translate/test_coverage_assertion.py` and
   `tests/translate/test_quantities_linear_time.py` hold the positive reader to their bounds on
   long untrusted texts. Five tests of the first
   repair that pinned a relation validated by its figures were rewritten to the stricter rule
   (the relation is stated in the task, or it is listed as unverified).

   Integration gate 1 rewrote existing tests only to a stricter rule or to an input that keeps the rule asserted; none was
   weakened or deleted: six STEM tests (listed in `docs/STEM_DESIGN.md`, section 35); `tests/branches/test_stem_pack.py`
   (its unknown unit is 'mth', since the year is a unit now); `tests/contract/test_receipt_plumbing.py` (the report-level
   hook is counted per caller: exactly once from the channel); `tests/integrity/test_integrity_round1.py`
   (`test_placeholder_reasons_and_bases_are_not_meaningful`: a blank reason or basis is now refused by the synthesis
   contract itself, asserted, and the ledger still reads it as not meaningful on an object built around validation); and
   the overseer's fixture verifiers declare the claims outside their scope (`channel.bus.CLAIM_OUT_OF_SCOPE`) instead of
   returning no outcome, which the channel now names NOT_ATTEMPTED (INT-REQ-006).

   Integration gate 2 (core: channel, integrity, translate, engine, ir, service, cli) rewrote one existing test to a
   stricter, reproducible rule and weakened or deleted none: `tests/engine/test_integration_gate1_engine.py`
   (`test_the_finding_case_gives_one_diagnostic_whatever_the_budget`) decided its case under wall-clock budgets of 50 and
   200 ms, so a slower machine or z3-solver 5.3.3 (which the dependency range allows) timed it out; the two budgets are now
   deterministic (the nonlinear policy's resource limit for the decision under a 60 s timeout, and the coverage probes'
   shared budget spent or whole), and each budget asserts its own state of the argument rules instead of accepting either
   at either budget. It passes with z3-solver 5.1.0 and 5.3.3. The gate's regression tests are
   `tests/integrity/test_integration_gate2_ledger.py`, `tests/channel/test_integration_gate2_channel.py`,
   `tests/translate/test_integration_gate2_translate.py`, `tests/engine/test_integration_gate2_engine_sweep.py` and
   `tests/service/test_integration_gate2_service_sweep.py`; their sweep tests feed every module's public text entry points
   the standard hostile inputs of `tests/core_hostile.py` (runs of about 20,000 characters) under a CPU-time bound per
   call, far above a linear reader's time and far below a quadratic one's.

   The gate-2 handoff fixer rewrote two existing tests to a stricter rule and weakened or deleted none:
   `tests/integration/test_stem_budget.py` (`test_a_spent_budget_leaves_the_stem_checks_undecided_never_success`) asserted
   one STEM check on the corpus answer ph-s1, which the rule named-restatement (`docs/STEM_DESIGN.md`, section 36) now
   reads as two (stem-eq-1 and the restatement stem-res-1); it now names each check and asserts every one ENTAILED when
   decided and undecided, never a success, when the budget is spent; and `tests/stem/test_layout.py` holds one more
   pattern of the STEM layout identical to the generic parser's (the linear line-of-marks pattern). Its regression tests
   are `tests/stem/test_integration_gate2_handoff.py` (the STEM layout's line of marks handed over by the parsers fixer,
   and the class sweep's quoted spans, joined lines and continued chains, with the run of accuracy marks the stem fixer
   asked for through the audited Physics hub), `tests/branches/test_integration_gate2_handoff.py` (the generic parser's
   joined lines and role assignment) and `tests/integration/test_integration_gate2_pins.py` (the solver pinned for a kit
   install: `integration/constraints.txt`, playbook step 6, the readiness row and `COMPATIBILITY.json`); each critical
   finding's worst-case input runs under a CPU-time bound with a wide margin and a growth ratio, and each rewritten reader
   is held to the reading it replaced on random input.

   Integration gate 3 (core: channel, integrity, translate, engine, ir, service, cli) weakened or deleted no test. It
   rewrote the core sweep tests of `tests/channel/test_integration_gate2_channel.py`, `tests/integrity/test_integration_gate2_ledger.py`,
   `tests/translate/test_integration_gate2_translate.py`, `tests/engine/test_integration_gate2_engine_sweep.py` and
   `tests/service/test_integration_gate2_service_sweep.py` into one test per hostile shape (`core_hostile.SHAPES`, `one`):
   the same entry points, inputs and per-call CPU-time bound, so the suite's 120 s wall-clock timeout per test no longer
   decides a sweep on a loaded machine (one sweep of 1,960 calls overran it at load average 12); the sweeps also gained
   entries (an introduced name, counts in words, `unbracket_elisions`, a hostile source claim cited by eight synthesized
   claims). `tests/core_hostile.py` gained the gate's shapes (formula constants "× 10", figures in scientific notation, number
   words around small counts; blank runs after a postposed "approximately", an unclosed mark "[1", a comparison, a note label
   and "per"). The gate's regression tests are `tests/integrity/test_integration_gate3_ledger.py` (the ledger's input stall
   and its class sweep, each rewritten reader held to its old form on random input; invented names, counts, relative dates
   and multipliers; dropped qualifiers; credits by a reporting verb), `tests/channel/test_integration_gate3_channel.py` (the
   relay and the response re-validate the delivered payload before any identity check; check names that are ordinary words
   of the subjects; the request and answer readers' blank runs) and `tests/translate/test_integration_gate3_translate.py`
   (the figure-ahead pattern end to end through `verify_claim`, the ratio-unit and elision patterns).

   Integration gate 3 (parsers: adapters, branches) weakened or deleted no test. It re-referenced six of the 570 texts of
   the general reading's reference corpus (`tests/branches/data/quant_general_reference.json`, `test_quant_si_reading.py`):
   texts that only mention self-certification ("a self-certification or forged receipt fragment", "the self-certifying
   sentence") or hold capital status words in a table of fixtures, which no longer get CORE-SELF-001. Each keeps its earlier
   digest as `sha256_before_gate3`, and `tests/branches/test_integration_gate3_quant.py` restores the earlier vocabulary rule
   and shows that every one of the 570 texts, these six included, then reproduces its earlier digest byte for byte, so the
   re-referenced digests differ by the self-certification rule alone. The gate's regression tests are
   `tests/branches/test_integration_gate3_quant.py` (a currency's direction against an exchange-rate unit: 'The franc fell
   from 25 to the pound in 1919 to 240 to the pound by 1926' and 'The mark fell from about 60 to the dollar in early 1921 to
   about 7,000 by the end of 1922' are ENTAILED, 'The franc rose from 25 to the pound to 240 to the pound' is still an engine
   error, a direction said of no named currency that holds only of the quoted one is undecided (CORE-QNT-001), derived
   changes hold of the rate as written or of the currency's value, exchange rates of two currencies are never compared;
   the reader is linear on long heads) and `tests/adapters/test_integration_gate3_parsers.py` (self-certification words that
   are ordinary content, "prints VERIFIED", "made no findings", "approved by the overseer", "checked and confirmed",
   "cross-checked", "via branch lines", are no CORE-SELF-001, INT-HANDOFF-006 or self-report-disclosed through the hub and the
   delivery policy's rule, while the receipt imitations, status labels and framed words stay named; the combinator's
   self-reports in prose, "..., which the engine confirms.", "All checks passed.", "This claim carries a signed engine
   result.", "QA: pass.", "(vérifié)", "The engine confirms this claim." and their class, are INT-LEDGER-029 on a synthesis
   and nothing on a specialist's branch, while History content about overseers and engines stays clean; every new pattern
   is linear). The parsers' sweep of the class found four input stalls in the shared readers, each
   fixed at its cause with possessive runs and held to the old pattern's reading on random input (same file): a bracketed
   verification label followed by a long blank run with no closing bracket ('[ok', '(verified': 2.5 s at 20,000 blanks, read
   for every sentence of every branch by CORE-SELF-001 and by the synthesis reading), the combinator's verdict term ('(overseer'
   with its optional key and colon, three adjacent runs: 8.8 s at only 1,000 blanks; '(audit'), the synthesis self-assessment's
   tail (1.5 s at 20,000 blanks) and the English citation 'Act I' (13 s at 20,000 blanks).

   The integration gate 3 handoff fixer rewrote two existing tests to the new rule and weakened or deleted none:
   `scripts/arena/test_arena_rules.py` (`test_only_the_two_forms_the_hub_gives_one_agents_stem_id_name_one_claim`, which the
   default suite does not collect) asserted that a History or English claim has no agent-qualified form (`qualification_tag`
   None); those parsers now qualify ids that collide, so it asserts each agent's exact tag (the digest-cut tag of
   `history-specialist@b` included) and keeps None for the generic branches; `tests/overseer/test_audit_fidelity.py`
   (`test_named_rules_are_listed`) pins the fidelity rules with the new `emphasis-figures` last and the earlier eleven in order.
   Its regression tests are `tests/branches/test_integration_gate3_qualified_ids.py` (two History instances, and English A:
   Literature with English A: Language and Literature, on one hub task: the second report's ids and every reference to them
   are agent-qualified, no INT-REQ-016, a faithful synthesis gets no INT-LEDGER-014, -002 or -023 and is not WITHHELD on the
   ledger's account, the overseer's re-parse raises no OVS-CUST-006, a single agent keeps its ids; the parsers' option on
   the hostile inputs), `tests/integration/test_integration_gate3_qualified_fixtures.py` (the kit's fixture provider serves a
   fixture recorded under the other form of a report's own claim id, as the arena does: without it the second History
   instance of a duplicate-mode turn got no outcomes and the turn was refused as incomplete, KIT-DL-011, and so had a second
   Physics instance's qualified claims since gate 1), `tests/overseer/test_integration_gate3_handoff.py` (a correct STEM
   result in `__…__` passes its audit, no OVS-FID-003; a wrong one is the engine's INT-SUBJ-001 and passes too; a figure the
   response states under no spelling is still FID-003 and digits joined by markers make up no figure; the fidelity readers
   swept) and
   `tests/channel/test_integration_gate3_handoff.py` (a joined middle-dot check's failure gives the engine's values per
   reading; and the class sweep of the modules it changed: the folded-tail count of `channel.bus` and of the ledger was
   searched from every digit of a run, quadratic in an unresolved issue a structured report may carry at any length, 2.4 s
   to receive and 2.5 s to audit 16,000 digits; the 'by' gap of a framed check was read from the outcome to every later name,
   1.47 s for one sentence of 80,000 characters; the premise value's lazy scan, which the core fixer had deferred as
   bounded by the IR's 1,000-character label; each held to its old reading on random input and run on its worst-case input
   under a CPU bound and a growth ratio).

   The round-8 clearance (integrated round c1) rewrote these existing tests to a stricter rule or to the rule a test's first
   version waited for, and weakened or deleted none (each docstring says what changed):
   - overseer (`tests/overseer/`): `test_repair4_label_only_data.py` (three tests), `test_repair5_statement_context.py` (one)
     and `test_rebuild_merged_translator.py` (two): the translator's pipeline now withholds the label-only and other-form
     circular encodings itself (E112, `translate/restatement.py`); each test first asserts that it does, then asserts what it
     asserted before on the translator with its semantic rule off (`conftest.without_the_translators_semantic_gate`).
     `test_rebuild_merged_translator.py::test_rule_semantic_restatement_reads_a_restatement_in_another_form`: "b and (b
     implies e)" (a link packed with its antecedent) moved to the controls (rule packed-link): the translator's semantic rule
     and the argument rules read it as an argument, and the overseer graded the delivered packed modus ponens OVS-TRN-006 (the
     receipt and the audit disagreed); "true implies e" is still a restatement; one more packed control was added.
     `test_corrections_adjudicated_faults.py`: record version 8 retires the three restored entries (kind
     `translator_semantic`); the tests of versions 2 to 7 keep every assertion on the data they read (the version-7 record is
     rebuilt from the shipped one), assert on the shipped record what it now holds, and make the assertions that re-derive a
     pipeline run version 7 recorded on the translator before the clearance; five version-8 tests were added (one of them
     parametrized eight ways). Two assertions are made differently, each said in its docstring: that a restored entry's
     evidence reproduces is asserted with its recorded pipeline run re-derived on the pipeline without the semantic rule
     (`pipeline_superseded`, which the loader now re-derives in full), since the pipeline as it is withholds it; and the
     restoration damages run on the version-7 record with p1-point and m7.1, m1.1 left out because on the translator before
     the clearance the overseer's reading of it now includes the translator's floor (its t_comp, named by the translator's
     semantic rule on the request's task record). `test_stem_repair12.py::test_the_repair_12_probes_name_every_plant_and_keep_every_control_clean`:
     the planted 'lin − 1000 = 0' is now withheld by the translator itself (probe outcome `withheld`, asserted first); the
     earlier assertions run with the translator's semantic rule off. `test_stem_repair10.py::test_d32_says_which_integrals_and_ellipses_are_checked`:
     pack 1.5's D32 (rule cut-decimal): "0.333… × 3 = 1" moved from the undecided constructs to the decided ones and "0.333… ×
     3 = 1.5" must fail. `test_stem_completion.py`: mai-t13's pinned count 13 -> 15 (rule cut-decimal adds two holding checks,
     the stated comparisons '5939.95… < 6000' and '6157.36… > 6000' on s12.3). The knowledge-pack tests that name "the next,
     unpinned version" (`test_knowledge_pack.py`, `test_knowledge_export.py`, `test_knowledge_examples.py`,
     `test_knowledge_drift.py`, `test_harness_contained_pack.py`) use 1.6, 1.5 being pinned now; the version pins
     (`test_knowledge_pack.py`, `test_knowledge_runner.py`, `test_integration_codes.py`) name 1.5, with 1.4 still pinned and
     loading.
   - overseer, missed by the clearance and repaired after it: `tests/overseer/test_rebuild_rekeyed_r7.py::test_the_overseer_raises_exactly_the_engine_shown_faults_on_the_recorded_translations_served_under_the_merged_ids`
     skips unless `EPINOIC_ARENA_ROUNDS` names the recorded rounds, so no verification run of the clearance executed it, and
     it still pinned OVS-TRN-006 on mai-t13 m1.1 and m7.1 while the clearance's translator withholds both (its semantic
     circularity rule, E112 at translation, decision 91) and record version 8 retires both (kind `translator_semantic`,
     decision 94): on the recorded r7 it failed with no error raised. A withheld translation gets no OVS-TRN finding
     (decisions 46 and 91), so the old pin contradicted the test's own `circularity-agreement` assertion and the shipped
     record. It was rewritten to a stricter rule, weakening or deleting none: `EXPECTED_WITHHELD` pins exactly the claims the
     semantic rule withholds on the pass (m1.1 naming t_comp, t_wants_euro and t_wants_value, m7.1 naming t_whole, and p7c
     h1.6 naming a_flow, each with E112 on both attempts and no OVS-TRN finding at any severity), the errors on the shipped
     pipeline are `EXPECTED_ERRORS` but the withheld claims (none), and the record's retirements are pinned (one on the genuine
     pass, five on this one, the two pinned claims among them). Every assertion it made on the two errors is made in the new
     `test_past_the_translators_semantic_gate_the_overseer_raises_the_pinned_faults_and_its_floor_on_the_same_encodings`,
     on the same pass with the translator's semantic rule off (`conftest.without_the_translators_semantic_gate`): the two
     errors exactly, plus the overseer's floor (`EXPECTED_FLOOR_ERRORS`: t_comp on m1.1, and p7c h1.6), each naming exactly
     the premises the translator's E112 names, and record version 7's entries matching the two. The new
     `test_the_pins_of_this_file_agree_with_the_shipped_adjudication_record` needs no recorded round, so a plain suite run
     fails when the file's pins and the shipped record drift apart again (with `EXPECTED_WITHHELD` empty, the pins before
     this repair, it fails).
   - overseer, round-8 r7 stage 2 (design Decision 111): no test was rewritten or removed. The new
     `overseer/tests/overseer_tests/test_r7_stage2_detection.py` pins three losses of detection the contained run of the round-8 commit
     showed against the base 16d5a4a: a declined-bound record whose stated count is not the recount (the T5c fault on a
     declining answer, ge-t14 with the channel's measure patched to 7, and a record stating no count) is OVS-FORM-003 naming
     MEASURED; tampering T5 presents a declined bound as decided and satisfied (RCPT-001), still flips a definitive status
     first, and never presents an unchanged receipt (`tamper.t5_presented`, SkipCase); rule derived-figures no longer traces
     a figure through the reciprocal of a precision end (bi-t13: 1/12.5 from "12 mm³") or a supplied text's precision end
     (ch-t13: 0.005 from "+/-0.01 s"), while every figure a supplied text states as written (a table cell, a per cent, a
     scale word, scientific notation, spaced thousands, the uncertainty itself) is still traced. All but one test need no
     recorded round; the last replays r7/ch-t13 (with `EPINOIC_ARENA_ROUNDS`), asserting first the decline and the four cases
     it makes skip with their reasons (T3, T5b, T22b, T22w), then T5 (RCPT-001) and T5c (FORM-003, MEASURED) detected. On the
     tree before the repair (with the new helpers stubbed to the old behaviour) 8 of its 18 tests fail.
   - STEM: `tests/stem/test_stem_repair10.py::test_a_cut_value_inside_an_expression_is_named_undecided_never_failed` is now
     `test_a_cut_value_inside_an_expression_is_decided_never_failed_when_correct`. It pinned ST-UNDEC-001 for every cut
     decimal inside an expression ('0.333… × 3 = 1') whatever its value, so a GDC-style answer was essentially unchecked; the
     STEM pack now reads a decimal cut by an ellipsis as one numeral whose half-width is a whole unit in its last digit (rule
     cut-decimal, `docs/STEM_DESIGN.md` section 39), so the correct lines must still hold with no finding and the wrong value
     ('0.333… × 3 = 1.5') must now fail. The fixes are pinned in `tests/stem/test_clearance_c1_stem.py` with the round's
     recorded STEM answers in `tests/fixtures/stem/round8/`.
   - parsers: `tests/adapters/test_integration_gate2_parsers.py::_old_governing_document` (the reference reading the gate-2
     equivalence test `test_the_credit_of_each_quotation_is_that_of_the_per_quotation_reading` compares the fast reader with)
     was rewritten to the c1 crediting rule: a name after a quotation in a later clause (a sentence stop, a comma before a
     conjunction or a spaced dash between them) credits nothing of it, and its cue spans (and `_old_named_before`'s) are read
     with the cue the structural reader reads by clause, `english_specialist.parser._TEXT_KIND_CUE_RE` (the literary kinds
     plus 'the text', 'the advertisement', ...; the whole-sentence `_TEXT_CUE_RE` keeps the literary kinds only). The test
     still checks equivalence on 6,000 random sentences. One reference datum was re-referenced, never weakened:
     `tests/branches/data/quant_general_reference.json` changed on one text ('Some 9,000 banks failed between 1930 and 1933;
     prices fell 25.5 per cent in January 1931.', since 'fell X per cent' with no 'by' is now read and named undecided,
     CORE-QNT-001); the item keeps its earlier digest as 'sha256_before_c1', and
     `tests/branches/test_c1_clearance_parsers.py::test_the_re_referenced_corpus_text_differs_by_the_fell_x_per_cent_rule_alone`
     restores the earlier pattern and checks that every one of the 570 texts reproduces its earlier digest byte for byte. The
     parsers' regressions are in `tests/branches/test_c1_clearance_parsers.py` (texts in `tests/branches/c1_texts.py`).
   - the clearance's handoff fixer: `tests/channel/test_c1_clearance_core.py::test_a_decline_is_named_and_no_item_reads_as_addressed_and_its_bound_is_decided_naming_the_decline`
     is now `..._its_bound_is_not_applicable_naming_the_decline`. Its first version asserted the interim behaviour it
     described as waiting for the transfer auditor (the bounds of a declined deliverable decided and charged INT-REQ-005 at
     error, naming the decline); the auditor now accepts the not-applicable record exactly when `withheld_deliverable` reads a
     decline in the journaled response (rule declined-bound), so the test asserts that record, the decline named, no
     INT-REQ-005 and no error. `tests/integration/test_turn_checker.py::test_prefetch_does_not_change_the_receipts`
     prefetches after the request is dispatched, with the task record the channel builds for it: the fixture corpus's
     verifier is task-aware now (the harness fixer's handoff), so the pipeline's first-attempt request carries the record;
     its assertions (equal receipts with the prefetch on and off, the prefetched proposals served) are unchanged.
     `tests/integration/test_fixture_parity.py`'s module fixture `arena_run` now comes from
     `arena_capture`, which runs the same round and also observes each genuine delivery's result digests (it returns the
     hub's own result unchanged), for the new G-EQ-ARENA digest test. The handoff fixer's regression tests are
     `tests/overseer/test_c1_handoff_bounds.py` (rules declined-bound and per-part-bound, and rule about-band: an "about N
     words" band missed by at most a quarter of N is a warning, a gross miss stays the error the round-5 test of en-t10
     requires; each with the audit agreeing and a control the audit names), `tests/channel/test_c1_handoff_channel.py` (questions as items,
     context and form sentences, "quoting", the short near miss), `tests/branches/test_c1_handoff_branches.py` (prose shares,
     criterion marks, the English pack that cannot load, and two input stalls: the core pack compared every quotation key with
     every other, and `nearest_text` read every supplied text again for every quotation, 10 s to receive 2,000 short
     quotations against a 21,000-character text), `tests/overseer/test_c1_handoff_shadow.py` (the shadow's rule composition,
     with the recorded ec-p8a material in `tests/overseer/data/`) and `tests/integration/test_fixture_parity.py` (the fixture
     path's task record); each module it changed has a sweep test over the standard hostile inputs.
     Its second pass (the STEM fixer's handoff items 2 and 4) rewrote three STEM tests to a stricter rule and weakened or
     deleted none: the channel now refuses a specialist's response whose own text holds a bidirectional embedding, override
     or isolate (INT-REQ-009, REJECTED, never delivered; rule bidi-text, STEM-integration finding 17), as the combinator
     port's text rule refuses one in a synthesis, so `tests/stem/test_clearance_c1_stem.py::test_a_relation_before_a_bidirectional_control_on_its_line_is_still_checked`
     and `::test_a_line_with_a_bidirectional_control_is_never_shown_as_checked` assert that refusal at the hub, and
     `tests/stem/test_integration_gate4_stem.py::test_an_invisible_mark_between_numerals_reads_as_a_blank` asserts it for its
     two bidirectional marks (U+2066, U+202A; the eight other marks as before); each keeps every assertion it made on what
     the STEM pack decides (rule bidi-control: the relation the control reaches named ST-UNDEC-001 and not decided, the other
     relations checked; ST-PARSE-001 and no failed check for the marks), now asserted on the pack itself, outside the channel.
     Its regression tests are `tests/channel/test_c1_handoff_bidi.py` (every subject and every control refused, the marks
     U+200E, U+200F and U+061C kept, a structured report refused on its claims' text, a supplied text the router's and not
     read for it, the readers linear on the standard hostile inputs and on a 400,000-character response),
     `tests/overseer/test_c1_handoff_bidi_audit.py` (the auditor re-derives the rule: a refusal passes, a channel that delivers
     such a response is OVS-RCPT-004) and `tests/stem/test_c1_handoff_mutation_sites.py` (the arena's STEM mutation sites,
     STEM-integration finding 25: no site in code, a mark annotation or a mark line; a site inside a quotation is also named
     by INT-REQ-003 and a term of a bracketed sum after its value by INT-SUBJ-004, beside the mutation's own code, which
     never changes; on c1 and r7 every mutated text is the one it was; the site readers linear), with the counting rule in
     `scripts/arena/test_arena_rules.py`.
     Its third pass (the core fixer's handoff item 2 and the parsers fixer's item 7, breadth item 19) rewrote no test: the
     core pack names a near miss of a name the supplied case states (rule case-name, CORE-SRC-008, warning), registered in
     `overseer.emitted` and in the code table of pack 1.5 before its first commit (1.5 pinned again with that row). Its
     regression tests are in `tests/branches/test_c1_handoff_branches.py` ('Tidewater Kayaks' on the Tidewell Kayaks case,
     the recorded bm-p8a answer with 'Brackwood' for Brackwater and the recorded answer clean, seven controls: a derived
     form, a name the request states, a sentence's first word, a name inside a quotation, four shared letters, a two-word
     place the case states and every name as the case writes it; the reader bounded on 15,000 to 20,000 hostile names and in
     the module's sweep).
   - the push check's hold on the clearance commit (rule meta-note, `overseer/meta_notes.py`; docs/DELIVERY.md 6b): the note
     form accepted any paragraph holding "not" or "only", so "Note: there is nothing to fix in this answer, not a single
     slip." was freed. A first rewrite read notes through a wide grammar with open slots, and an attack freed 196 of its
     332 assurance paragraphs through them ("Note: the figures come from Table 1 to the decimal place."); the rule is now a
     closed allowlist (a study suggestion whose object is the student's own work, a question or a passage of a strict
     source list that never names the answer's own part, a first-person inability to see or open a source named with a
     definite determiner, named content not checked and never set against the rest), so genuine notes outside it are
     refused by design. The fixer's own probe of the narrowed rule found 120 more paragraphs it still freed (a part of the
     answer learnt by heart or taken as a suggestion's object or yardstick, "your notes" as the object of practice, a
     submission, "the remaining figures are unverified", "I can't see a second source"); the last tightening closes them.
     The fix rewrote two tests of `tests/overseer/test_clearance_c1_overseer.py` to the stricter rule and weakened or
     deleted none: `test_a_next_step_or_a_note_that_reports_nothing_is_a_note` asserted eight notes; the six the allowlist
     refuses (lit-t14's task wording, ll-t14's provenance clause, en-p8c's status, use and possessive, a fictional-practice
     status, a suggestion naming the answer's own sentence, an extract's context not shown) moved to
     `NOTES_OUTSIDE_THE_ALLOWLIST`, asserted refused by the new `test_a_note_outside_the_closed_allowlist_is_now_a_self_report`,
     and the note list gained the allowlist's own reading of three of them ("Note: I can't see the image.", "Next step: plan
     your second analysis on the other passage now.", "Note: the dates are unchecked here.");
     `test_the_note_reader_reads_an_answer_of_two_thousand_notes_in_linear_time` read 2,000 "Note: the figures are practice
     data." as notes; it now reads 2,000 "Note: the figures are unverified." as notes and the old 2,000 as self-reports, each
     within the same bound. Every self-report of that file and its hostile paragraphs read as before. Its regression tests
     are `tests/overseer/test_c1_push_check_meta_note.py` (written with the first rewrite, rewritten with the allowlist: its
     two appraisals written as a suggestion's object, refused only by the vocabulary before, are now refused by the
     allowlist too; with the last tightening two of its own genuine controls, "Next step: annotate the second stanza,
     focusing on the verbs." and "Next step: annotate the opening stanza, then ...", moved from `FURTHER_GENUINE` to
     `OUTSIDE_THE_ALLOWLIST`, a stanza being a passage that can be the answer's own, and their strict-list readings, "the
     extract", took their place): the push check's three phrasings, 16 of the attack's bypasses and 7 of the probe's
     paragraphs on the recorded en-t14 answer through an audited hub with a delivery session (ES-META-001 kept, the
     self-report named, never FORMALLY CHECKED; the recorded answer alone names none), the label itself (with every claim of
     en-t14 counted clean, FORMALLY CHECKED with a genuine note and never with an assurance), all 332 paragraphs of the
     attack (`tests/overseer/data/meta_note_attack_round1.json`, two heading-led bypasses added that the first gathering
     skipped) refused by the rule and by the allowlist alone and kept on the pack path, the probe's 120 paragraphs refused
     by the rule and by the allowlist alone, 93 assurance phrasings (negated, double-negated, litotes, idioms, hedged,
     synonyms, every note lead, markdown emphasis, mixed with a genuine limitation, inside a suggestion, Spanish and French)
     refused, each by the allowlist alone too, 43 more in words neither vocabulary lists refused by the allowlist, negators
     alone refused, a genuine note with an assurance added refused, the allowlist's own lines each with both sides (a
     pronoun needs a noun phrase of its number and a topic names none; no suggestion names the answer; a yardstick is the
     student's own work or the strict list; practice only of the student's own work, a question or a practice item, and no
     verb of learning by heart; sending only back to the tutor; no universal, fidelity, finality or contrastive modifier on
     content not checked; first-person inability with a closed verb and a source named with a definite determiner; no
     character or word outside the lists; the lead decides the kind), the two recorded round-8 English notes it reads and 45
     further genuine notes kept, the five recorded English notes it refuses and 31 genuine notes outside the allowlist
     pinned as refused, receipt and audit in agreement (the task audit has no reading of a note; the receipt never frees a
     sentence the auditor's detector names), and the readers on 31 hostile paragraphs under the bound and on 13 growth
     ratios.
     Attack round 2 found rule meta-note held and every remaining bypass outside it, in the English parser's segmentation
     (a 'sources' unit, read before the meta-text test since the clearance commit, and a note-led 'body' block, at the
     published base already): rules lead-blocks and source-list (`overseer/meta_notes.py`, read by the delivery policy)
     refuse the label for any block of the answer as written that opens with a note or sources lead and is read neither
     as a note nor as a pure source list. The fix rewrote one test to the stricter rule and weakened or deleted none:
     `tests/overseer/test_c1_push_check_meta_note.py::test_with_every_claim_clean_the_label_rule_alone_refuses_en_t14_only_without_an_assurance`
     pinned the formal path's reasons for an assurance note as the ES-META-001 self-report alone (and its docstring said
     rule meta-note was then the only line, which round 2 showed false); rule lead-blocks names the same paragraph too, so
     it now asserts both reasons, the second naming paragraph 7 by position, lead and rule only. The same file's
     docstring of `test_every_paragraph_of_the_attack_on_the_first_rewrite_is_a_self_report` said 330 paragraphs; the data
     file holds 332 (196 of them freed by the first rewrite), as `docs/OVERSEER_DESIGN.md` Decision 99 now says too (it
     said 188 of 244). Its regression tests are `tests/overseer/test_c1_push_check_lead_blocks.py`, with the round's inputs
     in `tests/overseer/data/meta_note_attack_round2.json` (the bypass lens's 64 and the review lens's 25, each with the
     form its lens added it in): the 77 that carry a lead, or that the parser reads as meta-text, keep the recorded en-t14
     answer from the label with every claim counted clean (69 of them reached it with the rule switched off: all 53 of the
     bypass lens's and 16 of the review lens's), the block named (a paragraph after the answer, en-t14's own
     sources line replaced, a last sentence of its fourth paragraph, a sentence after its own note); the 12 with no lead
     that no reader names (plain body prose, a heading or a list item) are strict xfail tests, an open question for round
     9; the note-masking path recorded as open after attack round 1 (5 notes holding a quotation of the extract or opened
     by a fullwidth lead, which the parser reads as body) closed on the real path; the label for real on the Physics delivery fixture (FORMALLY CHECKED, and with a genuine note or a pure source list
     added, never with the push check's phrasings or another note-led or sources-led assurance); 22 genuine source lists
     read and 35 lists refused by rule source-list, every round-2 sources unit refused, a supplied name read only with the
     supplied titles, deny words beating a title, the closed list disjoint from the deny list; 54 lead forms (the History
     parser's leads and any blank the parsers read inside a lead among them), 5 leads split by a line break or an odd blank
     on the real path, 10 things that are no lead, the block's extent, the parser's paragraph cut, 8 leads rule meta-note has no reading of, the
     reason's words, the block bound; every lead block of the 18 recorded round-8 answers the repository holds pinned
     (only en-t14's two and ch-t14's sources line are read); the recorded English notes rule meta-note reads read as
     blocks too; receipt and audit in agreement (every block the auditor's structural detector names refused, the task
     audit the same with and without a note or sources block); and the readers on 14 hostile answers of up to 400,000
     characters under the bound and on 5 growth ratios.
     Attack round 3 showed a closed list of leads cannot close condition 6b (note leads the parsers read behind a format
     character, a bracket or a dash after "Note on", "N.  B."; the English parser's feedback furniture, answer notes and
     label-shaped "from memory" sentences; headings and list items; text a report delivered as an object never claims):
     rule non-material-text (`overseer/non_material.py`, read by the delivery policy) inverts the reading, so everything the
     branch's own parser reads as no claim, or that the journaled report does not claim, must be read by rule meta-note's
     note allowlist, rule source-list or the new strict rule layout; every reader normalises its text first and the lead
     reader reads any punctuation after a lead and any marks before it. The fix rewrote five tests to the stricter rule and
     weakened or deleted none, each change stated in its docstring:
     `tests/overseer/test_c1_push_check_lead_blocks.py::test_every_round_2_input_but_the_open_ones_keeps_en_t14_off_the_formally_checked_label`
     pinned every reason as rule lead-blocks' or the self-report's, and the meta-text heading's reasons as the self-report
     alone; rule non-material-text may now name the same block too. `::test_round_2_assurances_with_no_lead_are_open_for_round_9`
     held 12 inputs open (strict xfail); rule non-material-text closes three of them (a heading, a list item and a line with
     no stop, no claim for the English parser), now pinned closed by the new
     `::test_round_2_headings_and_list_items_are_closed_by_rule_non_material_text`, and nine plain-prose inputs stay open;
     `::test_the_round_2_data_covers_both_lenses_every_form_and_every_channel` counts them so.
     `::test_the_label_for_real_on_a_physics_answer_the_formal_path_completes_for` pinned rule lead-blocks' reason as the only
     one; rule non-material-text names the same block (the agent's report claims none of it), so both reasons are asserted.
     `tests/overseer/test_c1_push_check_meta_note.py::test_with_every_claim_clean_the_label_rule_alone_refuses_en_t14_only_without_an_assurance`
     pinned two reasons; the third, rule non-material-text's naming paragraph 7 by position and rule only, is asserted too.
     Its regression tests are `tests/overseer/test_c1_push_check_non_material.py`, with the round's inputs in
     `tests/overseer/data/meta_note_attack_round3.json` (the bypass lens's 111 en-t14 inputs and 16 Physics texts, the
     regression lens's 26 whole answers, each with the status the rules give it): the 52 en-t14 inputs the rules close keep
     the recorded answer from the label with every claim counted clean (37 named by rule non-material-text, 15 display spoofs
     by the lead reader), named by position and rule only; the 59 the English parser reads as claims of the answer (27
     material points and one material link the formal path marks not_eligible, 31 supporting interpretation sentences) and
     "NB all quotations hold." are strict xfail tests for round 9, their reading pinned; the 15 Physics assurances refused
     for real and the genuine note kept; text the agent's report never claims read however the parser reads it; the 26
     regression-lens answers refused; the label-level counterfactual for feedback furniture, an answer note and a
     label-shaped from-memory sentence; the push check's three phrasings (ES-META-001 kept, never FORMALLY CHECKED, named
     by rule non-material-text too); the 93 assurances of the meta-note corpus read by no closed reader and named appended
     or inline; the two recorded English notes and 45 further genuine notes leaving nothing unread (a bold-led note written
     inside a paragraph, which the parser glues to the sentence before it, refused conservatively), five on the real path
     with the label; rule layout (51 closed forms read, 32 refused) and its labels read by each parser's own pattern; the
     normalisation and the tag characters; 30 round-3 lead forms and 10 things that are no lead; the alignment of the
     parser's reading (a claim's own marks, mark annotations, order and whole words, the journaled report's claims, fail
     closed); each branch's reading (English, History, Economics, Physics, Mathematics) and an English answer whose report
     folds claims; every block of the 18 recorded round-8 answers the rule leaves unread pinned (only en-t14 has none);
     receipt and audit in agreement; and the readers on 9 hostile answers, 5 hostile layout blocks and 4 growth ratios.
     Attack round 4 found open slots in the fix's own readers: rule layout took the STEM parser's open part-id slot after the
     structure heads ("Working (fine):", "Method (good):", "Working ok:", "Known good:") and read runs of markscheme codes
     ("(A1) (A1) (A1) (A1)") as layout, rule source-list took words that name no source ("Sources: the examination paper's
     own answers.", "the extract's own lines"), look-alike letters hid a lead ("Nоte:" with a Cyrillic о, a Greek "Ν.Β."),
     and the task's wording was read once per block. The part id now takes only the parsers' own part-label grammar, a run
     of annotations is layout only when it holds mark allocations alone, the source list names sources and nothing else,
     every lead and label is read on the text's confusable skeleton (a lead only the skeleton reads frees nothing), and the
     task's wording is read once per answer. The fix changed eight tests, each to the stricter rule or to a corrected record,
     and weakened or deleted none, each change stated in its docstring or reason:
     `tests/overseer/test_c1_push_check_non_material.py::test_rule_layout_reads_closed_furniture` read the markscheme codes
     "(M1)" and "M1 A1" as layout; they moved to `::test_rule_layout_refuses_everything_else`, which also gained "Working
     (fine):", "Working ok:" and "Known good:". `::test_mark_annotations_the_parser_removes_inside_a_claim_do_not_break_the_reading`
     asserted nothing unread; the "A1" after the claim's last word is now a block rule layout refuses (the claim is still
     found across the "M1" inside it, and a mark allocation there is still layout).
     `::test_every_block_of_the_recorded_round_8_answers_the_rule_leaves_unread_is_pinned` gained maa-t14's sixteen codes
     (no block left the list). `::test_round_3_inputs_the_parser_reads_as_claims_are_open_for_round_9` held 59 inputs open;
     the look-alike lead among them is now closed, pinned by the new `::test_the_round_3_look_alike_lead_is_closed_in_round_4`
     (`CLOSED_IN_ROUND_4`; the data file is unchanged; `::test_the_open_round_3_inputs_are_read_by_the_english_parser_as_claims`
     reads the 58 left), and `::test_the_round_3_data_covers_every_input_of_both_lenses` counts 58 open; its reason, and that of `::test_an_assurance_with_no_lead_the_parsers_read_is_open_for_round_9` and of
     `tests/overseer/test_c1_push_check_lead_blocks.py::test_round_2_assurances_with_no_lead_are_open_for_round_9` (which said
     "pre-existing at the published base"), now state each input's behaviour at the published base as measured: FORMALLY
     CHECKED there on en-t14 without its note, withheld on en-t14 with it (that note's ES-META-001), so the claim channel is
     reachable on note-carrying answers since rule meta-note frees the note. Its regression tests are
     `tests/overseer/test_c1_push_check_round4.py`, with the round's inputs in `tests/overseer/data/meta_note_attack_round4.json`
     (the bypass lens's 158 label-level, 8 borderline and 83 literal inputs, the regression lens's 27 and the review lens's
     14, each with the form its lens added it in; the Physics fixture's answer as text, 20 inputs, and as its report object,
     14; and the behaviour at the published base 16d5a4a of every claim-channel input of rounds 2, 3 and 4, measured on
     en-t14 as recorded, on en-t14 shortened under the base's word bound with and without its note): the 145 inputs the rules
     close keep en-t14 from the label with every claim counted clean, named by position and rule only (the 13 look-alike leads
     by rule lead-blocks, the evaluative labels and wider source lists by their rules); the 145 the English parser reads as
     claims are strict xfail tests for round 9, their reading and their base behaviour pinned; on the Physics answer as text,
     for real, the push check's sentence, a look-alike lead, a lead alone on its line and the code runs are refused, the
     controls keep the label, and 10 claim-channel inputs (the STEM parser's 'structural' head through its own open slot
     among them) are strict xfail with their base behaviour; on the report object every evaluative label line and code run is
     refused and a part-labelled head, a run of mark allocations and a genuine note keep the label; rule layout's part-id
     grammar on every STEM head, its agreement with the STEM parser's head pattern, and 16 label lines of the lenses refused;
     11 code runs refused and 8 allocation runs read; 27 lists naming no source refused and 15 of the knowledge bases' forms,
     locators and kind tags read, the closed list holding source names only; 16 look-alike leads read as leads and freeing
     nothing, 4 look-alike labels cutting a block and never read as layout, the skeleton's table, the recorded and further
     genuine notes read as before; receipt and audit in agreement (the task audit the same with and without a round-4 block);
     the five recorded answers the 6b rules alone keep off the label with every claim counted clean and the one that keeps it;
     and the readers on 4 hostile answers of up to 400,000 characters, the task wording read once (4,000 blocks against an
     8,234-character task), and 3 growth ratios.
     Attack round 5 found the fix's own source-list reader reading only the words after its lead (the cutting reader takes any
     marks before a lead, an HTML-like tag and any mark after it, so "👍 Sources:", "★★★★★ Sources:", "🆅🅴🆁🅸🅵🅸🅴🅳 Sources:",
     "<all verified> Sources:" and "Sources💯" were freed), and the claim channel a regression since the published base (an
     assurance the branch's parser reads as a claim reached no reader, and rule meta-note made it reachable on note-carrying
     answers). Every reader that frees a block now reads it as a whole (before a lead or label only blanks, at most one list
     mark and the lead's own emphasis; the sources lead's colon), and the delivery policy's new refusal-only rule
     unverified-claims needs every claim of the answer, whatever its materiality, to carry a positive outcome of a signed
     engine result (a material claim marked not eligible, a supporting claim not clean and a parser claim whose whole text no
     journaled claim holds are named). The fix rewrote these tests to the stricter rule and weakened or deleted none, each
     change stated in its docstring:
     `tests/overseer/delivery_support.py::physics_report` gained `evidence=False` (default unchanged): the fixture's answer
     without its supporting evidence claim ("A car travels 120 km in 8 hours.", `p1.0`), which the fixture verifier never
     checks. In `tests/overseer/test_delivery_policy.py`, `::test_a_fast_clean_answer_is_refused_by_the_label_rule_alone_and_its_signed_receipt_verifies`
     (one verifier call of 5 s now, 10 s before), `::test_the_formal_path_makes_no_overseer_call`,
     `::test_a_report_with_several_claims_is_refused_by_the_label_rule_alone_only_when_every_one_is_clean` (30 s, 40 s before),
     `::test_inside_the_budget_the_formal_path_names_no_budget_reason`, `::test_a_tampered_receipt_or_payload_no_longer_verifies` (the reworded
     claim is the answer's first now), `::test_the_session_restores_the_channels_verifier_and_decides_once`,
     `::test_a_formal_path_never_waits_for_another_deliverables_overseer_stage` (B's answer) and
     `::test_the_delivered_payload_is_the_journaled_report` pinned FORMALLY CHECKED for the answer holding `p1.0`; they deliver
     the answer without it, and the new `::test_an_answer_holding_a_claim_no_signed_engine_result_decides_is_never_formally_checked`
     pins the refusal of the answer with it (withheld, the reason naming `p1.0 (supporting evidence: not_attempted)`; with
     overseer agents, the fallback). In `tests/overseer/test_gate1_overseer_fixes.py`,
     `::test_control_an_answer_whose_working_is_all_checked_is_refused_by_the_label_rule_alone` and
     `::test_control_the_same_answer_without_the_self_report_is_refused_by_the_label_rule_alone` likewise, with the answers of the tests they
     control (`_formal`, `::test_an_answer_carrying_a_self_report_never_travels_under_the_formal_label`) built without `p1.0`.
     The label tests of the four c1 push-check files counted only the eligible material claims clean
     (`_clean_formal_claims`), under which en-t14's 13 quotations and 6 interpretation sentences carried no outcome and en-t14
     is now refused by rule unverified-claims alone (pinned by the new
     `tests/overseer/test_c1_push_check_meta_note.py::test_with_only_the_eligible_material_claims_clean_en_t14_is_refused_by_rule_unverified_claims`);
     they count every claim of the recorded answer clean (`_clean_recorded_claims`; a claim the input adds keeps its real
     outcome) or, for a recorded answer delivered alone, every claim (`_clean_every_claim`):
     `test_c1_push_check_meta_note.py::test_with_every_claim_clean_the_label_rule_alone_refuses_en_t14_only_without_an_assurance`;
     in `test_c1_push_check_lead_blocks.py` `::test_with_every_claim_clean_the_recorded_en_t14_answer_is_refused_by_the_label_rule_alone`,
     `::test_every_round_2_input_but_the_open_ones_keeps_en_t14_off_the_formally_checked_label` (a reason naming a claim the
     input adds, condition 3's or rule unverified-claims', may stand beside the block's),
     `::test_round_2_headings_and_list_items_are_closed_by_rule_non_material_text`,
     `::test_a_genuine_source_list_in_place_of_en_t14s_is_refused_by_the_label_rule_alone`, `::test_the_note_masking_path_recorded_after_attack_round_1_is_closed`,
     `::test_a_lead_split_by_a_line_break_or_an_odd_blank_is_still_a_lead` and `::test_a_genuine_note_added_to_en_t14_is_refused_by_the_label_rule_alone`;
     in `test_c1_push_check_non_material.py` `::test_with_every_claim_clean_the_recorded_en_t14_answer_is_refused_by_the_label_rule_alone`,
     `::test_every_round_3_bypass_the_rules_close_keeps_en_t14_off_the_label` (claim reasons allowed beside),
     `::test_the_round_3_look_alike_lead_is_closed_in_round_4`, `::test_every_note_on_and_residual_answer_of_the_regression_lens_is_refused`,
     `::test_the_label_level_counterfactual_for_each_non_material_channel` and `::test_a_genuine_note_is_refused_by_the_label_rule_alone_on_the_real_path`;
     in `test_c1_push_check_round4.py` `::test_with_every_claim_clean_the_recorded_en_t14_answer_is_refused_by_the_label_rule_alone`,
     `::test_every_round_4_input_the_rules_close_keeps_en_t14_off_the_label`, `::test_a_look_alike_lead_is_named_by_rule_lead_blocks`,
     `::test_every_evaluative_label_and_wider_source_list_is_named_by_its_rule`,
     `::test_the_recorded_answers_the_6b_rules_alone_keep_off_the_label` and `::test_the_recorded_answer_the_label_rule_alone_refuses`.
     Their Physics helpers (`_physics` of the lead-blocks and non-material files, `_physics_report` of the round-4 file) build
     the fixture without `p1.0`; `test_c1_push_check_lead_blocks.py::test_the_label_for_real_on_a_physics_answer_the_formal_path_completes_for`
     and `test_c1_push_check_non_material.py::test_every_round_3_physics_input_is_refused_for_real_and_the_genuine_note_by_the_label_rule_alone`
     allow rule unverified-claims' reason beside the block's (the STEM parser reads some added sentences as claims the report
     does not hold). Two controls pinned the label for an answer holding a STEM structure head, "Working (b):", which the STEM
     parser reads as a 'structural' supporting claim no signed engine result decides:
     `test_c1_push_check_round4.py::test_the_physics_answer_delivered_as_text_for_real` and `::test_the_physics_report_object_for_real`
     now assert its refusal by rule unverified-claims alone, naming the claim. The strict xfail tests of the claim channel
     are real tests of the refusal now, renamed: `test_c1_push_check_lead_blocks.py::test_round_2_assurances_with_no_lead_are_open_for_round_9`
     (9) is `::test_round_2_assurances_with_no_lead_are_refused_by_rule_unverified_claims`;
     `test_c1_push_check_non_material.py::test_round_3_inputs_the_parser_reads_as_claims_are_open_for_round_9` (58) is
     `::test_round_3_inputs_the_parser_reads_as_claims_are_refused_by_the_claim_rules` and
     `::test_an_assurance_with_no_lead_the_parsers_read_is_open_for_round_9` (1) is
     `::test_an_assurance_with_no_lead_the_parsers_read_is_refused_by_the_claim_rules`;
     `test_c1_push_check_round4.py::test_round_4_claim_channel_inputs_are_open_for_round_9` (145) is
     `::test_round_4_claim_channel_inputs_are_refused_by_the_claim_rules`, and
     `::test_physics_text_claim_channel_inputs_are_open_for_round_9` (10) is split into
     `::test_physics_text_claim_channel_inputs_are_refused_for_real` (8) and
     `::test_physics_text_inputs_glued_into_the_verified_claim_are_refused_for_real` (2: the input is glued INTO the claim the
     engine verifies, whose fidelity review the fixture fakes, and the rule names a claim holding a note lead after a clause
     mark or a character outside the claim alphabet). Each asserts that the reasons name, by id only, the claim the input added
     or changed (`assert_claim_refusal`). Its regression tests are
     `tests/overseer/test_c1_push_check_round5.py`, with the round's inputs in `tests/overseer/data/meta_note_attack_round5.json`
     (the bypass lens's 156 lines, 22 of them weak praise emoji, each with the form and region it used; its 18 Physics text rows;
     the review lens's 83 whole-answer rows and 80 lines): every line read by no freeing reader; both block rules naming every
     en-t14 bypass; the lead region per reader (17 regions read for source lists and labels, 8 for notes, 62 refused for all
     three, 41 of them named by both block rules on en-t14 and all 62 keeping en-t14 off the label for real); the sources lead's colon (18 marks refused); a part label before a bulleted
     list read as two blocks; on the real path every en-t14 bypass and review answer refused (the block named by rule
     lead-blocks, or the claim named), the Physics text and report rows refused for real and their controls kept, the report
     object's glued symbols named by rule unverified-claims; the claim channel (12 en-t14 inputs and 6 Physics text inputs
     refused, the claim named), a material claim marked not eligible, claims that cannot be read, refusal only; receipt and
     audit in agreement; the claim alphabet (19 claims of letters, numbers, punctuation and mathematics read, 15 holding a
     character no encoding reads named, a radical with no operand among them) and the note lead glued into a claim (12 cases),
     the review lens's 2 symbols glued into the Physics result refused for real, and 3 inputs of words glued into the verified
     claim strict xfail (round 9: the fidelity review's); and the readers on 4 hostile regions, 200 long refused source lists
     and 4 growth ratios.
     Attack round 6 showed that no reader of free text closes condition 6b (assurances glued to a verified claim, eligible
     assurance claims, separate self-grades the verifier confirms, combining letters and hidden format characters the
     readers drop), so for the round-8 release rule `formal-label-withheld` (docs/DELIVERY.md condition 6d) withholds the
     FORMALLY CHECKED label from every answer and every answer takes the existing fallback. Every test that pinned FORMALLY
     CHECKED, or pinned a refusal's reasons exactly, pinned the older, weaker behaviour and was rewritten to the stricter rule,
     each saying so in its docstring; none was weakened or deleted. A pinned label now asserts that the label rule's reason
     is the formal path's ONLY reason (`delivery_support.assert_label_withheld_only`: every other condition still holds), and
     a pinned refusal asserts its reasons followed by the label rule's: `tests/overseer/test_delivery_policy.py`
     `::test_a_fast_clean_answer_is_refused_by_the_label_rule_alone_and_its_signed_receipt_verifies` (withheld without an overseer agent,
     overseer-selected and delivered with one, its payload the journaled one), `::test_the_formal_path_makes_no_overseer_call`
     (the formal stage still makes none; the fallback's overseer stage starts when it ends),
     `::test_a_report_with_several_claims_is_refused_by_the_label_rule_alone_only_when_every_one_is_clean`,
     `::test_an_answer_holding_a_claim_no_signed_engine_result_decides_is_never_formally_checked`,
     `::test_inside_the_budget_the_formal_path_names_no_budget_reason` (4; inside the budget the formal path names no budget reason, the
     fallback runs for the label rule only), `::test_a_tampered_receipt_or_payload_no_longer_verifies` (the answer is the
     fallback's; the mode tried is `formally_checked`, the accuracy tried "0/1"),
     `::test_the_session_restores_the_channels_verifier_and_decides_once`,
     `::test_a_formal_path_never_waits_for_another_deliverables_overseer_stage` (B's formal path is read while A's overseer
     stage holds its gate; B's fallback then waits for it, one overseer stage at a time) and
     `::test_the_delivered_payload_is_the_journaled_report`; `tests/overseer/test_gate1_overseer_fixes.py`
     `::test_control_an_answer_whose_working_is_all_checked_is_refused_by_the_label_rule_alone` and
     `::test_control_the_same_answer_without_the_self_report_is_refused_by_the_label_rule_alone`;
     `tests/overseer/test_c1_push_check_meta_note.py` `::test_with_every_claim_clean_the_label_rule_alone_refuses_en_t14_only_without_an_assurance`
     and `::test_with_only_the_eligible_material_claims_clean_en_t14_is_refused_by_rule_unverified_claims`;
     `tests/overseer/test_c1_push_check_lead_blocks.py` `::test_with_every_claim_clean_the_recorded_en_t14_answer_is_refused_by_the_label_rule_alone`,
     `::test_every_round_2_input_but_the_open_ones_keeps_en_t14_off_the_formally_checked_label`,
     `::test_a_genuine_source_list_in_place_of_en_t14s_is_refused_by_the_label_rule_alone`, `::test_a_genuine_note_added_to_en_t14_is_refused_by_the_label_rule_alone`
     and `::test_the_label_for_real_on_a_physics_answer_the_formal_path_completes_for`;
     `tests/overseer/test_c1_push_check_non_material.py` `::test_with_every_claim_clean_the_recorded_en_t14_answer_is_refused_by_the_label_rule_alone`,
     `::test_every_round_3_bypass_the_rules_close_keeps_en_t14_off_the_label`,
     `::test_every_round_3_physics_input_is_refused_for_real_and_the_genuine_note_by_the_label_rule_alone`,
     `::test_the_label_level_counterfactual_for_each_non_material_channel` and `::test_a_genuine_note_is_refused_by_the_label_rule_alone_on_the_real_path`;
     `tests/overseer/test_c1_push_check_round4.py` `::test_the_physics_answer_delivered_as_text_for_real`,
     `::test_the_physics_report_object_for_real`, `::test_the_recorded_answer_the_label_rule_alone_refuses`,
     `::test_the_recorded_answers_the_6b_rules_alone_keep_off_the_label` and
     `::test_with_every_claim_clean_the_recorded_en_t14_answer_is_refused_by_the_label_rule_alone`;
     `tests/overseer/test_c1_push_check_round5.py` `::test_en_t14_with_a_genuine_list_mark_or_emphasis_before_its_sources_lead_is_refused_by_the_label_rule_alone`,
     `::test_every_round_5_bypass_keeps_en_t14_off_the_label`, `::test_every_review_lens_row_on_the_physics_report_object_is_refused_for_real`,
     `::test_the_bypass_and_review_lenses_physics_text_rows_for_real`, `::test_the_physics_text_control_is_refused_by_the_label_rule_alone_and_the_rule_names_nothing`
     and `::test_with_only_the_eligible_material_claims_clean_the_supporting_claims_are_named`; and the strict xfail
     `::test_words_glued_into_the_verified_claim_are_open_for_round_9` (3) is a real test of the refusal now, renamed
     `::test_words_glued_into_the_verified_claim_are_refused_by_rule_formal_label_withheld` (the label rule its only reason).
     The integration kit agrees (its summary is never `formally_checked`): `tests/integration/test_decision_table.py`
     `::test_summary_from_counts` expected `formally_checked` for its first two rows and expects `partly_checked`;
     `::test_decision_table_vectors_match_the_hand_written_rows` pinned the vector `deliver-formally-checked` (its name kept)
     at `formally_checked` and pins `partly_checked`; `::test_a_non_definitive_status_never_yields_formally_checked` asserts no
     summary is `formally_checked` too. The regenerated vectors (`decision-table/deliver-formally-checked.json`,
     `chat-contract/labels.json`'s case `every-material-claim-positive-and-permitted`) are read by the JavaScript tests
     unchanged in code. Its regression tests are `tests/overseer/test_c1_push_check_round6.py`, with the round's inputs in
     `tests/overseer/data/meta_note_attack_round6.json` (the bypass lens's 17 en-t14 rows and 27 Physics text rows, the
     regression lens's 145 rows with their decisions at 16d5a4a and f2329df): the rule a named constant no configuration
     turns off; the label-level counterfactual (the clean Physics answer for real, en-t14 with every recorded claim clean:
     FORMALLY CHECKED without the rule, withheld by it alone); the push check's three phrasings; the clean answer
     overseer-selected with an overseer agent; every round-6 input never FORMALLY CHECKED, the rule's reason named (en-t14
     real and under two counterfactuals, the Physics text path real and with every eligible claim clean, every regression
     row as its lens delivered it); the inputs the label being off makes moot, which reach the label without the rule; an
     answer another condition refuses decided exactly as before (only the label rule's reason added); the kit's summary over
     every combination of up to three claims; the Worker's summarize; the readers that still run grow linearly.
     The pre-commit review of the c1 landing found five test problems, fixed without weakening or deleting a test, each
     change stated in its docstring. (1) Rule formal-label-withheld puts its reason on every formal path, so five end-to-end
     tests that asserted only "not FORMALLY CHECKED, some reason given" passed whatever the 6b and claim rules did:
     `tests/overseer/test_c1_push_check_round4.py::test_every_round_4_input_the_rules_close_keeps_en_t14_off_the_label` (145)
     and, in `test_c1_push_check_round5.py`, `::test_every_region_keeps_en_t14_off_the_label_for_its_sources_line_and_for_a_note`
     (62 regions, two answers each), `::test_every_review_lens_row_on_the_physics_report_object_is_refused_for_real` (30),
     `::test_every_review_lens_whole_answer_on_the_report_object_is_refused_for_real` (21) and
     `::test_the_bypass_and_review_lenses_physics_text_rows_for_real` (29). Each is stricter now: a refused row needs a reason
     other than the label rule's, from one of the rules its docstring names (the new `delivery_support.assert_refused_beyond_the_label`;
     the counterfactual without the label rule, `test_c1_push_check_round6._without_label_rule`, completes the formal path
     exactly when no such reason remains, so each row is never FORMALLY CHECKED without the label rule either). Measured on
     the landing, no row of the five is refused by the label rule alone; a few are refused before the formal path reads them,
     by the consolidation's exclusion of the answer, and are pinned so: the three quoted literal inputs of round 4
     (`QUOTED_LITERALS`) and the regions after a quotation mark of round 5 (`QUOTE_REGIONS`), a quotation of no supplied text
     whose receipt carries error-level findings, and the review lens's four "mid" whole answers, which the task audit names.
     With the 6b and claim rules switched off, 55 of the 59 rows of the two Physics text and report tests fail now (the 4
     controls pass); before, they asserted only what the label rule guarantees. The round-4 docstring now names rule unverified-claims (6c) and rule formal-label-withheld (6d).
     (2) The landing removed the only assertions on the text of the FORMALLY CHECKED label; they are pinned again on the label
     the counterfactual grants, in `test_c1_push_check_round6.py::test_the_label_level_counterfactual_a_physics_answer_every_claim_of_which_is_clean`
     (it starts "FORMALLY CHECKED within the 240 s translation budget", gives "each of the 1 material eligible claim(s)" and
     ends "This proves properties of the encodings only.") and `::test_the_label_level_counterfactual_en_t14_with_every_recorded_claim_clean`
     (the count of its material eligible claims, the budget and the scope statement). (3) Five tests whose names stated the
     opposite of what they assert are renamed, their assertions unchanged: in `tests/overseer/test_delivery_policy.py`,
     `::test_a_fast_clean_answer_is_delivered_formally_checked_with_a_signed_receipt` is
     `::test_a_fast_clean_answer_is_refused_by_the_label_rule_alone_and_its_signed_receipt_verifies`,
     `::test_inside_the_budget_there_is_no_fallback` is `::test_inside_the_budget_the_formal_path_names_no_budget_reason` and
     `::test_a_decision_never_waits_for_another_deliverables_overseer_stage` is
     `::test_a_formal_path_never_waits_for_another_deliverables_overseer_stage`; in `tests/overseer/test_gate1_overseer_fixes.py`,
     `::test_control_an_answer_whose_working_is_all_checked_is_still_formally_checked` is
     `::test_control_an_answer_whose_working_is_all_checked_is_refused_by_the_label_rule_alone` and
     `::test_control_the_same_answer_without_the_self_report_is_formally_checked` is
     `::test_control_the_same_answer_without_the_self_report_is_refused_by_the_label_rule_alone` (the passages above use the
     new names). (4) The base behaviour tests compare recorded data with itself and run no code at the base:
     `test_c1_push_check_round4.py::test_the_behaviour_of_each_open_round_4_input_at_the_published_base_is_recorded`,
     `::test_the_claim_channel_inputs_of_rounds_2_and_3_have_their_base_behaviour_recorded`, the `base_16d5a4a` assertions of
     `::test_the_physics_text_data_is_complete` and `::test_the_open_physics_text_inputs_are_claims_of_the_stem_parser_and_their_base_behaviour_is_recorded`,
     and the `at_16d5a4a` and `at_f2329df` assertions of
     `test_c1_push_check_round6.py::test_every_round_6_regression_input_is_never_formally_checked`. They are kept; their
     docstrings now say that the 16d5a4a and f2329df figures are recorded data, measured once by the attack lenses, not
     re-measured by the suite. (5) An exception raised by a refusal-only rule outside its own try block (rule meta-note's
     `self_report_findings`, rule lead-blocks, rule non-material-text, rule unverified-claims) escaped the formal path and
     made the whole decision WITHHELD for an internal failure, changing the delivery mode; `DeliveryPolicy._formal` now runs
     each fail closed, the exception a whole-answer reason naming the rule and the exception's type, the fallback deciding
     the mode. Its regression test, `test_c1_push_check_round6.py::test_a_rule_that_raises_refuses_the_label_and_changes_nothing_else`
     (4 rules, OVERSEER-SELECTED and NOT CHECKED), asserts the same mode as without the exception, the rule named, and,
     without the label rule, the clean Physics answer refused by the new reason alone; all 8 cases fail on the landing's
     policy.
     The re-review of those fixes found two more test problems, fixed the same way. (6) The five tests of (1) accept a
     reason of any one of several rules, so they catch the removal of all the rules they name, not of one of them while
     another also refuses the row (`assert_refused_beyond_the_label` now says so); the self-report reason (rules
     self-report-disclosed and meta-note) decided no row: with its reader switched off all 287 rows still pass. Those of the
     five that accepted it (`::test_every_round_4_input_the_rules_close_keeps_en_t14_off_the_label`,
     `::test_every_region_keeps_en_t14_off_the_label_for_its_sources_line_and_for_a_note`,
     `::test_every_review_lens_row_on_the_physics_report_object_is_refused_for_real` and
     `::test_the_bypass_and_review_lenses_physics_text_rows_for_real`) no longer accept it as the reason a row rests on
     (stricter; `test_c1_push_check_round5.SIX_B_DECIDING`). (7) Twelve more tests (ten names) whose names stated the label they no longer
     grant are renamed, their assertions unchanged: `::test_the_recorded_en_t14_answer_alone_reaches_the_label_with_every_claim_clean`
     (in `test_c1_push_check_lead_blocks.py`, `test_c1_push_check_non_material.py` and `test_c1_push_check_round4.py`) is
     `::test_with_every_claim_clean_the_recorded_en_t14_answer_is_refused_by_the_label_rule_alone`; in
     `test_c1_push_check_lead_blocks.py`, `::test_a_genuine_source_list_in_place_of_en_t14s_keeps_the_label` and
     `::test_a_genuine_note_added_to_en_t14_keeps_the_label` end in `_is_refused_by_the_label_rule_alone`; in
     `test_c1_push_check_meta_note.py`, `::test_with_every_claim_clean_the_label_is_formally_checked_only_without_an_assurance`
     is `::test_with_every_claim_clean_the_label_rule_alone_refuses_en_t14_only_without_an_assurance`; in
     `test_c1_push_check_non_material.py`, `::test_every_round_3_physics_input_is_refused_for_real_and_the_genuine_note_keeps_the_label`
     is `::test_every_round_3_physics_input_is_refused_for_real_and_the_genuine_note_by_the_label_rule_alone` and
     `::test_a_genuine_note_keeps_the_label_on_the_real_path` is `::test_a_genuine_note_is_refused_by_the_label_rule_alone_on_the_real_path`;
     in `test_c1_push_check_round4.py`, `::test_the_recorded_answer_that_keeps_the_label` is
     `::test_the_recorded_answer_the_label_rule_alone_refuses`; in `test_c1_push_check_round5.py`,
     `::test_en_t14_with_a_genuine_list_mark_or_emphasis_before_its_sources_lead_keeps_the_label` ends in
     `_is_refused_by_the_label_rule_alone` and `::test_the_physics_text_control_keeps_the_label_and_the_rule_names_nothing` is
     `::test_the_physics_text_control_is_refused_by_the_label_rule_alone_and_the_rule_names_nothing`; in
     `test_delivery_policy.py`, `::test_a_report_with_several_claims_is_formally_checked_only_when_every_one_is_clean` is
     `::test_a_report_with_several_claims_is_refused_by_the_label_rule_alone_only_when_every_one_is_clean` (the passages
     above use the new names).

   The third verification found finding 6 closed only for the claim and its supporting claims,
   and a regression of finding 1/9. `tests/translate/test_record_coverage_and_rounded_givens.py`
   tests both at the cause. Finding 6: a figure that a supporting claim, a supplied text or the
   task record asserts about a free conclusion symbol, and the encoding omits, is no verdict
   (E111) in every source, while the reviewer's own question, a possibility, a condition, a
   question, a negation, reported speech and a hypothesis keep W111 and the counterexample; a
   record's figure counts only in a clause about the symbol; a sentence that opens with a
   lower-case symbol ("Define b. n = 17.") is a sentence of its own, while a lower-case word
   that continues the sentence ("then", after "i.e.") is not; a question opened by a given
   does not govern the given ("Given n = 17, does b hold?"); a frame naming the task ("In this
   problem") presents its given, a hypothetical frame does not. Finding 1/9: a rounded given
   ("x is 0.33 to 2 decimal places", seven phrasings) grounds transcribed exactly and at exactly
   its stated tolerance, with the claim ENTAILED and released, while a wider, narrower or shifted
   interval, an interval for an exact or given figure, and one end from each of two figures do
   not; a rounded percentage states its interval in the symbol's declared reading; the stated-
   precision retry grounds and keeps its counterexample. Found while measuring (and present before this repair): a
   record that negates a figure in its own predicate ("x is not 0.33") established it; it establishes nothing now,
   while a negation of another figure and a bound phrase ("not more than") keep their readings. Two timing tests hold the new reading of
   long records (E111 over every figure, and the tolerance derivation) to the suite's 2 s bound.

   The fourth verification found finding 1 open in a cue-less wording of the reviewer's probe:
   in "If x = 1/3 then x = 0.33." the figure 0.33 was read as the rounded result of the written
   calculation "1/3 then x", so the faithful exact encoding was rejected for its stated precision
   and the widened retry was released. `tests/translate/test_calculation_result_and_cue_scope.py`
   tests the cause for the whole class: a figure is the result of a written calculation only when
   the calculation ends at its '=' (a word before the sign is no unit of the calculation unless the
   unit table, a currency or a scale word reads it; the calculation starts with an operand; the
   figure ends the expression), so every phrasing the verifier listed and their siblings (a
   connective, an arrow, a symbol, an identifier, an operator after a variable, a function symbol,
   an equation, a figure that starts the next expression) read the figure as unstated, and through
   the pipeline the faithful encoding is AMBIGUOUS_TRANSLATION after one provider call, never
   rejected for precision, never ENTAILED and never released, even under a review that calls it
   faithful; an approximation word or sign governs only the figure it is written against ("think
   about it", "almost certain", "about 2 people think that ...", "x ≈ 1/3 so x = 0.33" state
   nothing about 0.33; "without approximation" states exactness). Negative controls: calculations
   that end at the sign keep their readings (rounded, exact, or rounded by convention, LaTeX,
   exponents, count nouns, per cent words and function values inside a calculation included), the
   exactness cue keeps the counterexample, and a genuinely rounded claim uses its stated tolerance.

   The end-to-end simulation of 16 October 2026 found two channel and service bugs, tested at the
   cause. The combinator's synthesis (bug 7): `tests/channel/test_synthesis_vocabulary.py` pins that a
   synthesis carrying a value outside the synthesis contract's closed vocabularies (the simulation's
   free-text transformations verbatim, an alias, another spelling, a certainty, a materiality, a
   ledger entry, a conflict status) is REJECTED with INT-REQ-009 and INT-SYNTH-014 naming every
   claim without echoing the agent's text, also when the synthesis is an object built around
   validation (which was delivered before), while every documented transformation is still delivered
   and a valid synthesis gets the same receipt as a mapping and as an object; the harness side is in
   `scripts/arena/test_arena_rules.py` (a round whose syntheses carry free text, are not JSON, hold a
   claim that is not an object, lack a field or add one completes with a REJECTED synthesis record
   and its codes, never an exception; `list_claims.py --json` prints the contract's transformation
   values). The engine policy over HTTP (bug 8): `tests/service/test_named_policy_over_http.py` posts
   the simulation's eight recorded problems (`tests/service/data/`) with the policy their pipeline
   limits name and gets the pipeline's decision and the in-process binding (without a policy, the
   old answer), shows the policy bound into the result's identity and the release check's currency,
   refuses every name that is not exactly an allowlisted one before anything runs, keeps
   authentication, the rate and size limits and the self-certification refusal under every policy,
   and repeats one problem over a real local socket; `tests/engine/test_named_policies.py` pins the
   named-policy table and `tests/service/test_cli.py` the CLI's `--policy`.

   The same simulation left six injected faults unnamed (bugs 1 to 6), tested from its own answers
   (`tests/channel/data/e2e_run1_material.json`, copied verbatim) in
   `tests/stem/test_e2e_run1_detection.py`. The four detection gaps: the ch-e1b pH slip and
   substitution in `10^(−8.2)` are named INT-SUBJ-001 on s1.2 (a closed power with a non-integer
   exponent is one value: exact when it is rational, such as `16^(3/4) = 8`, else an enclosure decided
   in Form S; the substitution as the harness injects it, `10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³`, because
   an antilogarithm stated as a concentration is the concentration in mol dm⁻³, so an integer change
   of the exponent is no longer absorbed by the SI reading of the unit, and nine more such faults are
   named while the same concentration in any unit of concentration holds), the mai-e1 slip between LaTeX thin-space groups (`21\,131.40 − 18\,000`) on m10.1, and
   the hi-e1a misquotation of "the Mathematics specialist" is refuted with INT-REQ-003 on h1.5 (also
   "Maths" and "Math"); each genuine answer gains no error, correct work through irrational powers in
   an algebra step is never an error, and a quotation whose sentence names no text is still only
   unverifiable. The mai-e1 substitution in the annuity equation is named INT-SUBJ-001 on m3.1: an
   integer power beyond 12 of a closed value (`(1 + 0.065/12)^{-60}`) is one value (exact when it fits
   a literal, such as `2^{20}`, else the interval power; a power of an expression in symbols keeps the
   bound), and a decimal the answer states in prose for the quantity it named by a symbol ("Let $M$
   be the monthly payment" … "Her monthly payment is €352.19") is a stated root of the equation in
   it; the tests pin when that reading applies and seventeen answers in which it reads no root (a
   condition, a concession, a negation, a qualifier, a comparison, another quantity or part, a
   question, a value stated in maths, a whole number, a unit, no equation before the value, an
   equation outside the encodings, no name given to the symbol). The
   maa-e1a substitution (`P(t + 4) = P₀e^(k(t + 1))`) is named INT-SUBJ-001 on m3.1 by a model
   evaluation (`stem-mod`, UNSATISFIABLE), and the genuine answer's two model evaluations hold. The
   harness counts every injection no finding names as a miss: an earlier rule that reported such STEM
   injections "not applicable" excused real misses (the independent verification's probe round: a
   substitution of g with the mass stated only in prose, a slip with the spring constant stated only
   in prose), so it is withdrawn, and the probe round replays 27 of 29 with both misses listed; with no
   finding allowed to name anything every injection is a failure whose reason quotes the receipt's
   own ST-UNDEC findings; the injection is the base one (an exponent of ten moves its leading digit by
   3 like any figure, and four such injections are named); a contained round names all six faults.
   `tests/stem/test_model_evaluations.py`: an application of an exponential model the answer or the
   request defines (`P(t + 4)` after `P = P₀e^(kt)`, `N(10)` after `N(t) = 800 × (1/2)^(t/5)`) is the
   model at its argument; links with no solution are engine errors and correct ones hold, a letter
   defined as two models is read in either, round 7's maa-p7b gains three model checks that hold, the
   links the reading does not cover keep their old reading, and consecutive evaluations of a function
   the text defines (`N(10) = 200`, then `N(15) = 100`; `C(2) = 13`, then `C(3) = 18`), each an error
   at 22d6a5b, are no algebra step, while `ε = I(R + r)`, then `I = ε/(R + r)`, keeps its product
   reading and its step. `tests/stem/test_ascii_unit_exponents.py`: a unit exponent written in ASCII
   (`m s-1`, `mol dm-3`, `cm3`, `m/s2`) is read as the atom's power, so correct work in such units
   (an error at 22d6a5b: `3 m s-1` was `3 m s − 1`) holds and faults in it are errors, while
   `300 K-273`, `5 m-3 m` and `2 m2` keep their reading.

2. **Contained arena (bug testing with real agents).** Isolated specialist agents answer
   router tasks: the English and History specialists, configured only from their
   knowledge documents. Every output crosses the hub exactly as in production. The harness
   (`scripts/arena/run_arena.py`) then repeats each answer with injected faults: an
   invented quotation in double or single marks, an altered quotation, a
   self-certification, wrong arithmetic and a wrong chronology. A fault counts as caught only
   when a finding of the expected code names the injected claim or quotes the injected
   words. Each round also includes a peer exchange: one specialist's delivered report is
   forwarded by the router to the other specialist, who quotes it. That specialist reads only
   the delivered report, its document id and the relay status (`relayed/<task>.json`), never
   the hub's receipt of it, which stays in the router's record (`router/<task>.json`); the
   regression tests are in `scripts/arena/test_arena_rules.py`. The same file holds the
   integration gate's first-round harness fixes: the combinator's synthesis reaches the hub as
   written, its citations included (an invented id beside a real one is named INT-LEDGER-001,
   and a peer group's combined output gets the receipt of a direct relay from either member's
   file, listing every delivered report); a syntheses file out of the combinator port's
   published output contract (a control or bidirectional character, a blank text or reason, a
   repeated citation, a key or field the contract does not have) is a named failure with its
   KIT-CB code (`combinator_contract`); and the delivery pass's auditor declares every key id
   the hub's components sign under, so a result the cross-agent check signs is not audited as
   untrusted (OVS-RES-003). The integration gate's second round added the case of two STEM
   agents in one group, whose second report the hub delivers with agent-qualified claim ids
   (`s1.2@physics-specialist`): `list_claims.py` lists every file under the ids the hub delivers
   (each member parsed after the members delivered before it, with the request text the STEM
   parsers read), a translation recorded under either form of one agent's STEM claim id serves
   that claim and is named on the record (it was lost before, and the genuine receipt carried no
   outcome), and a mutation, delivered with the unqualified ids on a hub task of its own, is
   compared with its genuine record in its own id form. Round 7 replays as before (177 of 177,
   every record unchanged apart from the fixture coverage's new, empty
   `served_under_other_id_form`); rounds 1 to 6 hold no STEM report, so none of this applies
   to them. Round 8's clearance made the replay run what production runs wherever a recording
   allows it, and name what it cannot (`metrics.replay`, summary.md's "Replay configuration"
   line): the claim verifier receives the task record of each request, as production's does
   (`--without-task-record` replays as before); `scripts/arena/bind_translations.py` records with
   each translation the digest of the claim text it was produced for, as a step of recording a
   round; a retry served the same recorded output is reported as not exercised; and a synthesis
   is stamped when it is relayed. Round 8 replays 201 of 203 with and without the task record
   (10 genuine claims change their displayed status as production computes them;
   `docs/ARENA_RESULTS.md`). The regression tests are in `scripts/arena/test_arena_rules.py` (the
   round-8 section: each fails on the harness before the fix).

   Three independent overseer agents then judge the round:
   - **Results audit** checks every receipt against its input.
   - **Communication fidelity** compares each answer, sentence by sentence, with what the
     router received, and runs its own exchanges.
   - **Adversarial** builds hostile variants of the round's answers.

   Fixer agents, each owning one area of the code, fix every blocker and major with a
   regression test. The suite and the harness on every earlier round must pass before the
   fix is committed.

3. **Stress testing.** Load on the engine, the channel, the branching hub, replays of the
   real arena outputs (sequential, 16 threads and the HTTP service), plus the
   stress-marked suite. Full tables are in `docs/STRESS_RESULTS.md`.

## Bug testing results

### Overseer verdicts per round

A rate is the share of transmissions the overseer judged right: correct receipt and
faithful payload. The target is 0.98 from all three overseers.

| Round | Results audit | Communication fidelity | Adversarial | Findings (blocker / major / minor) | Earlier findings confirmed fixed |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.909 | 0.909 | 0.850 | 33 (8 / 15 / 10) | first round |
| 2 | 0.560 | 0.488 | 0.612 | 49 (2 / 24 / 23) | not separately counted |
| 3 | 0.727 | 0.769 | 0.871 | 37 (0 / 17 / 20) | 44 of 49 |
| 4 | 0.387 | 0.575 | 0.890 | 44 (1 / 26 / 17) | 35 |
| 5 | 0.366 | 0.617 | pending | 30 so far (0 / 15 / 15) | 25 so far |

Every round used fresh answers from the isolated agents on new texts and topics. From
round 2 onward each round also included a peer exchange through the hub. The rates do not
rise steadily, for two reasons. First, the overseers judge every delivered payload, not
just the injected faults. Second, each new round brings answer shapes the code had not
met: arithmetic stated across two sentences, verdicts worded in new ways, and quotations
credited to the wrong source in the peer exchange. A falling rate on fresh material
therefore points to coverage still missing; it does not mean the earlier fixes failed.
Most of the earlier findings were confirmed fixed in the next round (last column).

### Harness results on every recorded round (current code)

| Round | Functional transmissions |
| --- | --- |
| r1 (four tasks) | 26 / 26 |
| r1-adv (hostile variants of round 1) | 148 / 151 |
| r2 | 41 / 41 |
| r3 | 41 / 41 |
| r4 | 41 / 41 |
| r5 | 41 / 41 |

The three r1-adv misses:
- **Empty response:** the hub correctly rejects it. The harness's "a genuine answer is
  delivered" rule counts that as a miss, and it is reported rather than relabelled.
- **Two injected faults in a 1,189-word unpunctuated bullet block:** a wrong percentage
  and a reversed date order. The hub still raises the engine-decided error (INT-SUBJ-001),
  but the finding does not point at the injected claim. The stricter rule added in round 4
  therefore does not count it. This is open.

### What the overseers found, by theme

- **Hand-off integrity** (rounds 2 and 3, fixed):
  - A specialist could relay a forged copy of a colleague's report and overwrite the
    report the router held.
  - Relays were not checked against the plan's agents.
  - A re-delivered report id silently replaced the first delivery.

  The envelope is now bound to the payload's owner, and held reports are never
  overwritten. Duplicates and changed payloads are named.
- **Receipt robustness** (fixed):
  - About 440 arithmetic sentences overflowed the receipt summary and raised out of the
    hub.
  - A lone UTF-16 surrogate in an answer raised out of the hub.
  - Brace-like text made parsing quadratic.
- **Arithmetic and chronology:**
  - Fixed: month-year dates between figures, shared units, trillions, folds and fractions,
    figures in words, circa, year ranges, same-month dates, and relative clauses.
  - Open from round 5: arithmetic that is not a per-cent, point, fraction or fold change,
    for example "added roughly 4,500 miles".
  - Open from round 5: relations stated across sentences.
  - Open from round 5: ordering cues other than before and after, for example "ran from
    31 May 1902 to ...".
  - Open from round 5: "nearly" and "almost" read as two-sided bands.
- **Parsing fidelity:**
  - Fixed: inline from-memory labels, JSON pasted into prose, nested and mixed quotation
    marks, guillemets, stanza breaks, long elisions and diacritics.
  - Fixed: notes are never a paragraph's point.
  - Still open: self-certifications worded outside the recognised shapes.
  - Still open: the requested verdict delivered as a supporting claim when it is not
    worded like earlier examples.
  - Still open: a sentence about how the answer was built becoming the material point.
- **Attribution in peer exchanges:**
  - Fixed: an unlocated quotation is never credited to the first supplied text.
  - Fixed: reporting clauses credit the outer speaker.
  - Open: a History answer crediting the English specialist's words to the poet, when the
    poem is not among the History request's supplied texts.
- **Combinator fidelity:**
  - Fixed: changed figures and dates, and swapped figure-event pairs.
  - Fixed: conflicts cited without a conflict record.
  - Open: changed decades, degree verdicts, who holds a view, and small counts written in
    words.

The full reports with reproductions are kept with each round's material and are summarised
round by round in `docs/ARENA_RESULTS.md`.

## Stress testing results

| Iteration | What ran | Result |
| --- | --- | --- |
| 1: engine | 1,000 sequential verifications; 16 threads vs sequential; 12 adversarial payload types × 20; 16 hard problems at 100 ms; 45 s soak | 219.5/s, p50 4.4 ms, p95 5.7 ms; thread results identical; 0 INTERNAL_ERROR; timeouts bounded (worst 523 ms); memory growth 0.02 to 0.06 MB |
| 1: channel | 300 router→specialist→router cycles; 16 threads; 8 specialists accumulating 120 formalised claims; 200 adversarial responses | p50 4.6 ms; 640/640 threaded cycles accepted; contradiction named on the final receipt; 120 rejected, 80 delivered with findings, 0 crashes |
| 1: branching hub | 100 cycles per subject branch | p50 0.8 to 11.5 ms per cycle depending on the branch |
| 2: arena replay | 180 sequential transmissions of real outputs; 16 threads (672); 400 HTTP requests | p50 18.6 ms, p95 26.7 ms; 0 rejected under threads; the service sheds load with 503 above its admission bound |
| 2: finding | the same replay with the service admitting 64 concurrent requests | **Segmentation fault**: the engine's memory budget was per verification while Z3's limit is process-wide, so 32 concurrent verifications exhausted it. Fixed by scaling the limit with the number of verifications running; a stress test now runs 32 concurrent verifications. |
| 3: arena replay after the round-2 fixes | the same three legs | 400/400 HTTP requests served; 0 crashes; but p50 rose to 37.3 ms (from 18.6) |
| 3: finding | profiling the slowdown | Each excerpt was re-located in every supplied text and the text re-normalised each time, and sentence splitting and date tokenizing were quadratic. Fixed with caching and linear algorithms: the suite went from 140 s to 23 s with identical receipts. |

The next stress pass runs at the end of the current arena loop, then again in each of the
three clearance rounds, and then at scale (many agents per task). Its numbers will be added
here.

## Arena round 8 (integrated round c1)

Measured results only. The round's harness summary is marked QUALIFIED (fixtures unbound).

| Measure | Value |
|---|---|
| Arena run time | 289.4 s |
| Peer deliveries | 4 of 4 dependencies |
| Transfers judged / dossiers | 30 / 60 |
| Overseer instances / duplicates spawned | 4 / 0 |
| Verdicts valid / invalid | 60 / 0 |
| Agent-findable faults present / named | 30 / 1 |
| Accusations: confirmed / unresolved / refuted | 1 / 20 / 1 |
| False accusations accepted | 0 (the one false accusation was caught by a deterministic check) |
| Contested transfers / resolved | 9 / 0 |
| Repeated-fault transfers stopped | 3 of 8 (held for human review; 5 were green-lit) |
| Contradictions of signed results / caught | 0 / 0 |
| Green-lit transfers | 17 |
| Genuine transfers | 12 |
| Overseer time total / median per instance | 4524.9 s / 1163.8 s |

Gates:
- False-accusation gate: NOT MEASURED (bounds 0.0 to 0.078 of clean transfers), because 8 unresolved accusations on clean transfers need human adjudication.
- Every verdict produced by the package's runner: FAIL (all verdicts were self-reported).
- Injection gate: NOT MEASURED.

Green-lit transfers later found inaccurate on review (partial list; the source data was cut off):
- t1f22e0: minor arithmetic slip in an intermediate step; final result correct.
- t2fab05: wrong intermediate unit, and a sources line citing notes that were not supplied (both minor).
- t3159a5: major. The answer told the student every claim was verified, while the signed receipt was ACCEPTED_WITH_FINDINGS with unsupported and ambiguous claims. A non-success status was shown as success.

These results are agent self-reports scored against signed engine results; they prove properties of the encoding only.

## What runs next

- **English/History arena loop:** continues from round 5 until all three overseers reach
  0.98.
- **STEM support (Physics, Chemistry, Mathematics, Biology, ESS):** built inside the same
  infrastructure, in the worktree `.worktrees/stem`, with its own:
  - labelled corpus,
  - adversarial audits,
  - contained arena of stand-in STEM specialists.

  It is merged once it passes them.
- **After both:**
  1. Three rounds of overseer bug tests, fixes and stress tests on the combined
     infrastructure.
  2. Scaling to any number of agents per task, with its own stress report.
  3. A contained test with many duplicated English and History agents, optimised while it
     runs.

Each step adds its results to this file.

## Progress (updated every hour while the builds run)

**2026-10-12 00:30 UTC.** The four builds resumed after a pause caused by an account spend limit:
- the English/History arena loop;
- STEM support;
- the logic-checking overseer agents;
- the breadth probe of eight further specialists.

The arena loop now stops at round 10 at the latest (at most 10 rounds in all). From round 7:
- its specialists use the v3 knowledge bases;
- a fourth overseer measures the translation model claim by claim against the 98% target.

The overseer build now also oversees the translator agents: each proposed claim-to-IR
translation is audited and appears in the overseer agents' dossiers.

The verified baseline, `3147d08`, and its review are recorded in `docs/BASELINE_REVIEW.md`.
Work in progress after it is labelled as such.

**2026-10-12 02:45 UTC.**
- **Publication.** The verified baseline was published to Bruno's private repository at
  about 00:35 UTC, as branch `import/translator-baseline` (`650d1d3`). Its tree is identical to
  the baseline (`3147d08`, tree `cc82e93`) plus documentation.
- **Interruptions.** Between 00:30 and 02:40 UTC the four builds were resumed twice. Both times
  an account usage limit stopped them within minutes, and the round-6 fixers were cut off again.
- **Round 6.** The round-6 work so far is checkpointed as `4461ab2`: default suite 1,504 passed,
  1 skipped. That checkpoint is work in progress. Its harness replays and the overseer re-check
  are still to run.
- **Final-only publishing.** From now on, Bruno's repository is updated every hour on branch
  `verified-updates`, and only with final fixes. A final fix is one of these verified arena
  commits:
  - "Fix the rN arena overseer findings";
  - "Fix defects found by the contained stress runs";
  - "Arena results: …".

  The full suite must be green, and no replayed round may score lower than in the last update.
  Work-in-progress commits are never published. Nothing qualifies yet.
- **Builds.** The four builds resumed at 02:41 UTC.

**2026-10-12 03:30 UTC.**
- **Arena round 6.** Fixes are still in progress. The English, History and harness fixers
  have finished, and the channel fixer is still working. The round's verified commit follows
  once the suite and the replays of every recorded round pass.
- **Overseer build.** The live hook stage is committed on its own branch (`6bb22b7`). Its
  contained-test harness is being built now.
- **STEM build.** It is in its checks stage.
- **Breadth probe.** It finished all its steps. Its 45 distinct findings feed the first
  combined clearance round.
- **Stress tests.** Per Daniel's instruction, no stress tests run after bug fixes, and no model
  is stress tested. The only load testing will be the scalability tests with many agents on
  the infrastructure, in the scaling step and the multi-agent test.
- **Bruno's repository.** Nothing is final yet, so nothing new was sent.

**2026-10-12 04:27 UTC.**
- **Arena round 6.** Verified and committed (`23707b9`). The full suite has 1,617 tests, all passing. The harness
  counts are r1 30/30, r1-adv 150/151 and 46/46 for each of r2 to r6. This was the first verified update sent to
  Bruno's repository.
- **Arena round 7.** It now uses all sixteen specialists from the v4 knowledge bases, on the cheapest model tier,
  each reading its whole knowledge base as a single bundle. The task design has 22 tasks covering all sixteen
  specialists, with three cross-subject peer pairs. Each pair shares one group, so the hub can relay between them:
  - Economics to Business Management;
  - Physics to Mathematics: Analysis and Approaches;
  - History to English A: Literature.

  The specialists are answering now. The STEM build joins round 7 if its implementation is committed before the
  round's checks begin, after an independent verification; otherwise it joins round 8.
- **Plan changes requested by Daniel.**
  - Bug-testing rounds come first. The optimisation checks (at most three) now run last, after every bug-testing
    round, and the stand-alone optimisation pass was stopped.
  - Rounds 8 to 10 run after the STEM and overseer builds merge. In those rounds the overseer agents run on the
    cheapest tier under the self-duplication protocol.
  - The multi-agent test uses all sixteen specialists, not duplicated agents.
  - Every update to Bruno's repository now includes an update README.
- **STEM and overseer builds.** Both were interrupted at 03:45 UTC and resumed at 04:28 UTC from their last
  completed steps. Their unfinished edits were backed up first.
- **Bruno's repository.** No new final fix this hour, so nothing new was sent.

**2026-10-12 05:27 UTC.**
- **Arena round 7, material.** The material is complete:
  - 22 answers from all sixteen specialists, on the cheapest model tier from the v4 knowledge bases;
  - 22 translations and 22 syntheses;
  - 3 of 3 cross-subject peer reports delivered through the hub (Economics to Business Management, Physics to
    Mathematics: Analysis and Approaches, History to English A: Literature).
- **Arena round 7, harness before fixes.** 161 transmissions, 148 functional (91.9%). 13 failed; most are
  syntheses, along with one peer answer. 35 genuine answers or syntheses carry findings to be judged. The full suite
  has 1,617 tests, all passing. The overseer lenses will now decide which findings are real defects.
- **STEM in round 7.** The STEM build was not merged into round 7: its routing and corpus-evaluation stages were not
  committed when the round reached its harness. It joins at round 8, after the merge.
- **Builds.** The STEM build is in its routing stage and the overseer build in its contained-test harness stage.
  Neither has a new commit this hour.
- **Bruno's repository.** No new final fix this hour, so nothing new was sent. Round 7's verified fix commit is the
  next candidate.

**2026-10-12 06:28 UTC.**
- **Arena round 7, overseer agents.** Three cheapest-tier overseer instances reviewed 30 blind dossiers built from
  a copy of the round, 10 each, using the exported knowledge pack. All 30 verdicts passed the package's validation.
  Against the gold labels they named 52 of 123 injected faults, with no false accusation.
- **Arena round 7, communication-fidelity lens.** Rate 0.4246. It confirms 13 previous bugs fixed and reports
  18 new ones: 1 blocker, 11 major and 6 minor.
- **Arena round 7, other lenses.** The results-audit and adversarial-live lenses are running now; the
  translation-fidelity lens follows. Owner-partitioned fixes and the verified commit come after.
- **Builds.**
  - The STEM build committed its routing stage and is now on corpus evaluation.
  - The overseer build committed its contained harness (tampering suite, dossier export, verdict scoring) and is
    building the consolidation and self-duplicating pool stage.
- **Bruno's repository.** No new final fix this hour, so nothing new was sent.

**2026-10-12 07:28 UTC.**
- **Arena round 7, lens verdicts.** None of the four lenses reaches 98%. They report 66 new findings in all:
  3 blockers, 45 majors and 18 minors.

  | Lens | Rate | Previous bugs confirmed fixed | Blockers | Majors | Minors |
  | --- | --- | --- | --- | --- | --- |
  | results-audit | 0.532 | 8 | 1 | 14 | 7 |
  | communication-fidelity | 0.4246 | 13 | 1 | 11 | 6 |
  | adversarial-live | 0.7477 | 13 | 1 | 12 | 2 |
  | translation-fidelity (translation accuracy) | 0.6384 | first round | 0 | 8 | 3 |

  The rates fall from round 6 because round 7 adds fourteen new subjects. The owner-partitioned fixers are working
  now; the round's verified commit follows.
- **STEM build.** Corpus evaluation is complete. All 38 injected faults are named, and no error-level finding falls
  on correct work. Its suite has 3,470 tests passing and 4 expected failures, each marked against a documented
  existing defect. It is writing its documentation and joins the arena at round 8.
- **Overseer build.** Its first adversarial review found 31 defects: 1 blocker, 22 majors and 8 minors. The fixes are
  in progress.
- **Bruno's repository.** No new final fix this hour, so nothing new was sent.

**2026-10-12 08:27 UTC.**
- **Arena round 7 fixes.** The English fixer fixed 10 findings and the channel fixer 18. Items that need another
  owner's files, or the STEM or overseer builds, were written as handoffs: 10 from the English fixer and 9 from the
  channel fixer. The history and harness fixers are working now. The round's verified commit follows the full suite
  and the replay of every recorded round.
- **STEM build.** Finished on its own branch: all 38 injected faults named, no false errors on correct work, suite
  green. It joins the arena at round 8.
- **Overseer build.** Its first review round fixed defects in tamper evasion, agent abuse and precision. Its second
  review round is running.
- **Bruno's repository.** No new final fix this hour, so nothing new was sent.

**2026-10-12 09:27 UTC.**
- **Arena round 7, verified.** The fixes are committed (`dc77853`) with the round's results report (`99e435b`).
  Round 7's harness now passes 162 of 162 transmissions, against 148 of 161 before the fixes. The full suite has
  1,855 tests, all passing (1,617 before). No earlier round dropped: r1 30/30, r1-adv 150/151, and 46/46 for each of
  r2 to r6. Before their fixes, the four lenses had rated round 7 at:
  - results-audit 0.532;
  - communication-fidelity 0.4246;
  - adversarial-live 0.7477;
  - translation accuracy 0.6384.

  Testing continues in rounds 8 to 10, after the STEM and overseer builds merge. Findings that need the STEM or
  overseer code are kept in handoff files and applied after those merges.
- **Bruno's repository.** The second verified update was sent to `verified-updates` (from source `99e435b`). It
  carries `UPDATE_README.md` (what changed, the bugs found, the fixes, the before and after counts) and a note
  backfilled for the first update.
- **Overseer build.** Its second review round is in its fix stage. The STEM build is complete and waiting to merge.

**2026-10-12 14:11 UTC.**
- **Overseer build stopped, then resumed.** At about 09:50 UTC the organisation's monthly spending limit stopped the
  overseer build during its second review round's fix stage. The hourly checks from 10:27 to 13:29 UTC did not run
  while the session restarted. A one-agent capacity test succeeded at 14:09 UTC, and the build resumed from its cache
  at 14:10 UTC. Its unfinished edits were backed up first; the steps that failed at the limit run again. No spending
  limit was changed.
- **Arena and STEM build.** Unchanged since 09:27 UTC: round 7 verified, STEM waiting to merge at round 8.
- **Bruno's repository.** No new final fix since the 09:27 UTC update, so nothing new was sent.

**2026-10-12 15:27 UTC.**
- **Overseer build, review round 2 fixed.** The round's 26 findings (18 blocker or major) are fixed on the build's
  own branch (`cda154c`). Afterwards the transfer audit detected all 110 tamperings, with no false alarm on any of
  the 72 genuine transfers. The full suite has 2,145 tests passing (6 skipped recorded-round tests pass when pointed
  at the recorded rounds). Arena round 3 replays at 41 of 41 transmissions.
- **Overseer build, review round 3.** Two of the three reviews have finished. Tamper evasion found 14 issues (1
  blocker, 11 major, 2 minor). Agent abuse found 6 (4 major, 2 minor). The precision review is running; the fixes
  follow.
- **Bruno's repository.** No new final fix on the development branch, so nothing new was sent. The overseer build
  reaches it through phase 2's verified merge.

**2026-10-12 16:27 UTC.**
- **Overseer prototype on Bruno's repository.** On Daniel's instruction the overseer build is now uploaded to Bruno's
  repository on its own branch, `overseer-prototype`, and updated hourly with final commits only. The first upload
  (16:13 UTC) is the build's review-round-2 commit (`cda154c`). Before the push, the full suite was re-run on exactly
  that tree, with every recorded round available: 2,151 passed, none failed or skipped. The upload carries an update
  note listing the changes, the review findings and fixes, and the findings still open.
- **Overseer build, review round 3.** All three reviews are in: 25 findings (1 blocker, 19 major, 5 minor), against
  26 in round 2 and 31 in round 1. The round-3 fix step is running.
- **Bruno's `verified-updates`.** No new final translator fix, so nothing new was sent.

**2026-10-12 17:27 UTC.**
- **Overseer build stopped by a weekly usage limit, then resumed.** At 17:08 UTC the account's weekly usage limit
  stopped the round-3 fix step after 58 minutes of work, before anything was committed. Its unfinished edits were
  backed up, two one-word capacity tests succeeded, and the build resumed from its cache at 17:23 UTC; the round-3
  fix step is running again. No spending limit was changed.
- **Publishers.** The overseer upload scripts were checked by three independent review rounds; the last found no
  blocker or major, and its small findings are fixed. No new final commit on either branch this hour, so nothing new
  was sent to Bruno's repository.

**2026-10-12 17:45 UTC.**
- **Where testing stands.** Seven of the ten bug-testing rounds are done (r1 to r7; r7 was the first with all sixteen
  specialists). Rounds 8 to 10 run in phase 2, after the STEM and overseer builds are merged. A live round takes about
  2 to 5.5 hours (r4 2h20, r5 3h40, r6 5h30, r7 5h20); replaying one recorded round through the translator code takes
  6 to 9 seconds and is used as the functional simulation before every upload.
- **Translator.** After the round-7 fixes the replay passes 162 of 162 transmissions and the suite 1,855 tests. The
  reviewers' ratings of round 7 before those fixes were translation accuracy 0.64, results-audit 0.53,
  communication-fidelity 0.42 and adversarial-live 0.75; the fixes are re-rated by live reviewers in round 8, so the 98%
  target is not yet demonstrated.
- **STEM translator.** Built and evaluated on its own branch (all 38 injected faults named, no false errors); it joins
  the arena at round 8.
- **Overseer build.** Round-3 review fixes in progress (25 findings: 1 blocker, 19 major, 5 minor). The contained
  simulation of the uploaded overseer prototype passes rounds 2 to 5 (41 of 41 each, 110 of 110 tamperings detected) and
  fails on round 7 (139 of 143 functional, 3 false alarms, 235 of 254 injected faults named), because its translator
  base predates the round 5 to 7 fixes; no further overseer code is uploaded until it passes, which the phase-2 merge
  addresses.
- **Uploads.** From now on an update is pushed every hour, with or without new final code. Every push is preceded by a
  simulation of exactly the uploaded code (full suite and every recorded round), and the replaced version is kept in
  the repository as a backup branch.

**2026-10-12 18:28 UTC.**
- **Overseer build, review round 3 fixed.** The round's 25 findings (20 blocker or major) are fixed on the build's own
  branch (`87eaf86`, 18:11 UTC): 26 fixes, 6 items left undone and listed. Afterwards the transfer audit detected all
  110 tamperings, with no false alarm on the 72 genuine transfers, and the suite has 2,244 tests passing (2,145 at
  round 2). Arena round 3 replays at 41 of 41. The build has moved on to its contained rounds, in which overseer
  agents configured only from the exported knowledge pack review live transfers.
- **Uploads.** The hourly update of `verified-updates` carries no new code (the round-7 version), checked by a fresh
  simulation before the push. The round-3 overseer commit is uploaded to `overseer-prototype` only if its full
  simulation passes, including round 7.

### Progress, 21:58 UTC

- STEM support merged into the translator (commit 83e97e9) and published to `verified-updates`: full suite 4,353 passed (45 stress tests deselected, 4 strict expected failures); harness r1 30/30, r1-adv 150/151 (the planted empty answer stays REJECTED), r2 to r6 46/46, r7 177/177 (the 162 recorded transmissions plus 15 STEM mutation variants, all 15 named).
- Overseer build: contained-round c1 fixes committed on the build branch; its evaluation gave 2,281 tests passed, 110 of 110 tamperings detected and 0 false alarms on rounds 2 to 5. On round 7 the overseer still fails two contained gates (99 of 118 arena faults named and confirmed; 3 false alarms, all from one circular-translation check); the correction and a rebuild on the STEM-merged translator are in progress.
- Arena round 8 is prepared: 24 tasks over all sixteen v4 specialists, with four peer pairs (two humanities pairs, one STEM pair, one STEM-humanities pair).

### Progress, 22:58 UTC

- Overseer build: the faults its round-7 simulation exposed are corrected on the build branch (commit ef4ba9f). On rounds 2 to 5 and 7 the contained run now gives 0 false alarms on genuine transfers (3 before), both genuine round-7 circular translations raised as errors and recorded with engine evidence, the redundant restatement in bm-t13 reported as a warning, 110 of 110 tamperings detected and 250 of 254 arena faults named and confirmed; the 4 remaining misses belong to the build's older translator and go with the merge of the current translator, now in progress. Overseer suite: 2,385 passed.
- Specialist feedback: a code review found that no finding is sent back to the specialist that produced an answer (receipts go only to the router); a feedback and revision function is being added with the overseer rebuild.
- External review findings: engine-side fixes for five findings (premise authority, core-dependent safeguards, stale results, counterexamples to faithful definitions, limits in the binding) pass the reviewer's own probes on a work branch (suite 4,430 passed there); they join the development branch after integration and verification.

### Progress, 01:00 UTC

- External review findings: all nine fixes integrated and committed (engine 0.4.0, policy 2026.10-v4, translator 0.4.0, integration contract 0.2; see `REVIEW_FIXES_README.md`). Full suite 5,264 passed (45 stress tests deselected, 4 strict expected failures); every recorded round replays unchanged: r1 30/30, r1-adv 150/151, r2 to r6 46/46, r7 177/177. Published to `verified-updates`.
- End-to-end simulation of the website-to-backend flow (sixteen specialists, fourteen simulated student requests, contained; no live provider): the deterministic stages took 4.49 s for all sixteen tasks (at most 0.81 s per request); the engine over HTTP answered in 9.7 ms at the median and 23.2 ms at the 95th percentile; 156 of 156 engine verdicts reproduce; 96 of 102 injected faults were named. All 29 error-level findings on correct answers were false and the combinator's syntheses were refused by their schema; both are being fixed.
- Overseer rebuild on the STEM-merged translator: 5,985 tests passed and all eleven contained-run gates pass (round 7: 133 of 133 injected faults named and confirmed, 0 false alarms; 72 of 72 tamperings detected). One finding is open: a circular translation that rests only on unverified grounding labels is reported as a warning instead of an error; the repair is in progress.
- Argument-defect audit (planted cases across the subjects): of 44 defects, 16 were named, 9 were caught without a name and 19 were missed; 7 of 22 clean controls were flagged. Named argument diagnostics (leaps in logic with the missing link, unchecked sources, formal and informal fallacies, STEM method errors) are being added.

### Progress, 02:00 UTC

- Argument diagnostics: a scoring corpus of 101 cases was built (44 planted defects across formal fallacies, evidence, informal reasoning and STEM method; 57 clean controls, 35 of them correct answers from the end-to-end simulation). On the current verified code, 9 of the 44 defects are named, 25 are caught without a name and 10 are missed, and 41 of the 57 clean controls are flagged; the fixes are measured against this corpus and a separate hold-out corpus.
- Channel and service fixes from the end-to-end simulation (on a work branch, not yet integrated): a combinator synthesis with an unknown transformation is now a named rejection instead of an exception, and the HTTP service accepts a named, allowlisted engine policy bound into the result's identity; 5,395 tests passed there, and every recorded round replays unchanged.

### Progress, 03:00 UTC

- Overseer rebuild on the STEM-merged translator, fourth repair: 6,033 tests passed; every recorded round replays unchanged (r1 30/30, r1-adv 150/151, r2 to r6 46/46, r7 177/177); all eleven contained-run gates pass, with 269 of 269 injected faults (including the 15 STEM mutations) named and confirmed, 134 of 134 tamperings detected and 0 false alarms on genuine transfers. Its independent audit is running; STEM completion, the fast profile and the oversight planner follow before the commit.
- Failure review: every earlier failed agent run had stopped on account usage limits, not on a code fault. The review lenses that never completed (STEM soundness, STEM precision, parser safety, correctness, translation fidelity, security, combinator faults, formal robustness, router and envelope, robustness and contracts) are being run again on the current verified code.

### Progress, 04:00 UTC

- Overseer rebuild: the independent audit after the fourth repair found three remaining problems (one medium: a numeric self-proving translation is only warned about when the request mentions the figure inside a negation or a question; two low: overseer dossiers built from recorded rounds do not yet carry STEM translations, and one knowledge-pack line describes model instructions for STEM translations as enforced rules). The fifth repair is in progress.
- End-to-end fixes: both fix branches are complete and are being integrated and independently verified together.

### Progress, 11:00 UTC

- End-to-end fixes committed (8a78efe, "Fix the end-to-end simulation findings") after independent verification accepted all eight bugs on its third pass: decimal powers of ten and LaTeX thin-space thousands separators are read, substitutions are caught by the detection itself, an altered quotation is named, malformed combinator output is a named rejection, the HTTP service carries a named engine policy, and plain-text unit exponents (dm-3, s-1) are read as exponents. 5,667 tests passed, no test was removed, and every recorded round replays unchanged (r1 30/30, r1-adv 150/151, r2 to r6 46/46, r7 177/177).
- Overseer rebuild: STEM completion staged (6,251 tests passed, every recorded round unchanged, all thirteen contained-run gates pass with 0 false alarms). Its independent STEM audit found six remaining gaps (among them an SI-prefixed ohm not read as a unit and a dimension check missed when one side has a single unit-bearing operand); the first STEM repair is in progress. The fast profile and the oversight planner are deferred.
- Argument diagnostics: all five fixers finished (fixers a to e, each with regression tests; the re-run review findings in their files are included). Fixer c alone names all 12 STEM-method defects of the development corpus with 0 false alarms; the five branches are now being integrated and then verified on the development and hold-out corpora.

### Progress, 12:00 UTC

- End-to-end fixes are on the main repository's verified line (uploaded 10:46 after a simulation of exactly that code).
- Overseer rebuild: the first STEM repair closed the earlier audit's gaps; the second independent STEM audit, with its own new planted faults, found eight more (two high: integer division and modulo written as the words mod and div are read wrongly and graded as errors; a given that contradicts the request is not named). The second of at most three STEM repairs is in progress; the rebuild is committed only after a clean audit.
- Argument diagnostics: the five fixer branches are being merged onto the current development branch (with the end-to-end fixes) before independent verification on the development and hold-out corpora.
- Integration kit: the protocol and kit passed their fresh-session playbook check on the third verification (two medium contract items remain open for the next step); the combinator sub-project is being built.

### Progress, 13:00 UTC

- Argument diagnostics: the five fixer branches are merged and staged on the development branch with the end-to-end fixes (suite green; every recorded round replays unchanged; development corpus 44 of 44 defects named with 0 false alarms on 57 controls). The independent detection-accuracy check measured the hold-out corpus at 48 of 66 defects named (9 more caught but not named, 9 missed) and 13 of 68 controls flagged, short of the acceptance bar (95% named, at most one control flagged), and found two new false alarms caused by the changes. The repair loop (at most five rounds) addresses them; a second, sealed hold-out corpus written without sight of the fixes is being prepared as the final generalisation check before commit.
- Overseer rebuild: the second STEM repair is in progress; the rebuild is committed only after a clean audit.
- Combinator sub-project: built; its first verification found one medium item, now being repaired.

### Progress, 14:00 UTC

- Argument diagnostics: all four independent checks of round 1 reported (detection accuracy 25 issues, safety and invariants 6, adversarial probes 14, re-run review findings 21; 66 in total, 11 of them high, including two regular-expression slowdowns on hostile input and one loosened contradiction check). Repair round 1 of at most five now works on all 66. A second hold-out corpus of 136 cases (70 defects, 66 controls), written and audited without sight of the fixes and sealed by checksum, will be the final generalisation check: on it the committed code names 23 defects and flags 31 controls; the staged changes before repair name 41 and flag 22. Nothing is committed until every check passes.
- Sub-projects: the flash router is published as a standalone branch (its own history; 19 tests pass on the split tree alone, with the translator's port definitions from the same commit for the conformance tests). The combinator follows when its verification is clean; its second check found 3 medium and 5 low items, now being repaired.
- Overseer rebuild: the second STEM repair is in progress.

### Integration protocol, kit and combinator: measured results (19:00 UTC)

- 28bca5c merged the integration protocol and kit (specialist, checks, overseer, combinator and flash-router ports; Z3 and STEM required) and the combinator sub-project into the translator. Independent check: 6,832 tests passed, every recorded round unchanged (r1 30/30, r1-adv 150/151, r2 to r6 46/46, r7 177/177), hygiene scan clean.
- The pre-upload simulation of 28bca5c found one environment-dependent false failure in a readiness test (it required the caller's EPINOIC_ variables to reach the service, the opposite of the kit's documented behaviour). 0aaa20e corrected the test to check that nothing of the caller's leaks in and that the service sees exactly the kit's own variables; an independent check confirmed the correction is stricter. Suite on a clean export: 6,832 passed, 0 failed, with and without EPINOIC_ARENA_ROUNDS set.
- Known open items, carried into the integration gate before round 8: in the combinator, a source claim already marked as a note can be carried into a synthesis without a finding (high), plus three medium items (short or irregular dropped hedges, a unit or prefix rescaling, some crediting forms); in the kit contract, two medium items (a material claim skipped by the budget outside the listed claims; a BaseException escaping the turn checker).
- Pre-upload simulation of 90d395c (the merge above with the readiness-test correction, on a clean export): suite 6,832 passed, 45 deselected, 4 xfailed; every recorded round replayed with its recorded count (r1 30/30, r1-adv 150/151, r2 to r6 46/46, r7 177/177).

### Progress, 20:00 UTC

- Integration kit: the work-directory placeholder is now `<workdir>` (86ab0ba). Independent check: every change is the
  rename or its manifest digest; the playbook tests assert the same things; suite 6,832 passed, 45 deselected,
  4 xfailed, with and without the recorded rounds.
- Overseer rebuild: the fourth STEM repair is in progress. Its last audit reported 8 issues (3 high); 41 of 57 planted
  STEM faults were caught and 34 of 41 clean controls stayed clean.
- Argument diagnostics: verification round 2 is in progress (corpus check 17 issues, 4 high; invariants 5, 1 high; the
  adversarial and re-run checks are still running). After the first repair, on the sealed hold-out set: 58 of 70 faults
  caught, 44 of 70 named, 47 of 66 clean items left clean.
- Phase 2 waits for the overseer rebuild commit; round 8 follows the merges, the delivery rule, the argument-diagnostics
  merge and the integration gate.

### Progress, 22:00 UTC

- Overseer rebuild: the fourth STEM repair is still running (its input: 8 audit issues, 3 high: two false errors on correct
  Boolean and physics working, and an unchecked "± %" uncertainty). Last measured tree: 6,580 tests passed, 13 of 13
  contained-run gates, 15 of 15 STEM mutations named.
- Argument diagnostics: the second repair is running on the 46 issues of verification round 2 (7 high; 17 from the
  corpus check, 5 invariants, 12 adversarial, 12 from the re-run review).
- Phase 2 waits for the overseer rebuild commit. Nothing new was published since 3ecb88e (20:04).

### Progress, 23:00 UTC

- Overseer rebuild: the fourth STEM repair measured 6,731 tests passed, every recorded round at its recorded count, 13 of
  13 contained-run gates, 0 false alarms on genuine transfers, 15 of 15 STEM mutations and 269 of 269 arena faults named
  and confirmed. Its independent audit found 4 issues (1 high: false errors on four shapes of correct physics and
  computer-science working; down from 8 issues, 3 high). The fifth STEM repair is running.
- Argument diagnostics: the second repair is running (46 issues from verification round 2, 7 high).
- Phase 2 waits for the overseer rebuild commit.

### Progress, 01:00 UTC (18 October)

- The final handoff report and the website launch package are on the main repository's `docs/final-z3-handoff` branch
  (`9c4f463`); the source pin there is unchanged (`verified-updates` code `3ecb88e`, from `86ab0ba`).
- Overseer rebuild and argument diagnostics resumed at 00:36 UTC from the work staged when they were stopped: the fifth
  STEM repair and the second argument-diagnostics repair are running. Their loops now end when the independent checks
  report no high-severity issue; medium and low findings are recorded as known defects.

### Progress, 17:00 UTC (23 October)

- Work stopped at the weekly usage limit on 18 October (about 22:55 UTC) and resumed after its reset on 23 October at
  16:15 UTC; nothing was committed or pushed in between.
- Overseer rebuild: the sixth STEM repair is running against the last audit's 4 issues (1 high: false errors on four
  shapes of correct physics and computer-science working).
- Argument diagnostics: repair round 2 is running on the 46 issues from verification round 2 (7 high, 25 medium, 14 low).
- Deployment package: the two surveys are finished; the retarget design step is running.
- Phase 2 waits for the overseer rebuild commit.

### Progress, 18:00 UTC (23 October)

- Overseer rebuild: the sixth STEM repair has finished its measurements and is writing the results (still running).
- Argument diagnostics: repair round 2 on the 46 round-2 issues (7 high) is still running.
- Deployment package: the kit retarget is implemented; its independent checks (diff review and a cold-start rehearsal of
  the playbook) are running.
- Phase 2 waits for the overseer rebuild commit.

### Progress, 19:00 UTC (23 October)

- Overseer rebuild: the sixth STEM repair measured 6965 tests passed, 152/152 probe answers named and 130/130 controls
  clean, all 13 contained-run gates passed and 15/15 STEM mutations named; the independent audit then found 1 high issue
  (givens written without "=" or in a colon list get no check, while the pack says every given has one). The seventh STEM
  repair is running.
- Argument diagnostics: repair round 2 measured 8062 tests passed, 44/44 development defects named with 57/57 controls clean,
  and 65/66 hold-out defects named with 68/68 controls clean. Verification round 3 found new high-severity issues (corpus 3,
  invariants 2, re-run findings 1; adversarial 13 issues); repair round 3 follows.
- Deployment package: the cold-start rehearsal passed on its second check; the diff review has one medium issue left and its
  second repair is running.

### Progress, 20:00 UTC (23 October)

- Overseer rebuild: the seventh STEM repair is regenerating the pack schemas and docs after its fixes. From now on its repair
  loop also repairs medium-severity audit findings (false alarms on correct work, pack text that disagrees with the code)
  before the rebuild is committed, within a bound of 12 repairs; low findings stay known defects.
- Argument diagnostics: repair round 3 is running on the round-3 findings.
- Deployment package: the kit retarget passed its independent checks; the package is written and in its second review.

### Progress, 21:00 UTC (23 October)

- The kit retarget to the retrained agents repository is committed (f34ff1d: suite 6866 passed, integration tests 796
  passed, every recorded round unchanged) and uploaded to verified-updates after its simulation passed. The deployment
  package for a new session is committed under docs/handoff/z3-deployment (99e647f).
- Overseer rebuild: the audit after the seventh STEM repair found 3 problems; the next repair is running. The repair loop now
  also clears medium-severity findings before the rebuild is committed.
- Argument diagnostics: repair round 3 is running.

### Progress, 22:00 UTC (23 October)

- Overseer rebuild: the eighth STEM repair is fixing the 3 problems of the last audit (1 high: a false alarm on correct STEM
  working with equations; 1 medium: derivative relations neither checked nor named; 1 low).
- Argument diagnostics: repair round 3 is still running.

### Progress, 23:00 UTC (23 October)

- Argument diagnostics: repair round 3 measured 8249 tests passed (round 2: 8062), every recorded round functional,
  44/44 development defects named with 57/57 controls clean, and 65/66 hold-out defects named with 67/68 controls clean
  (1 new false alarm). Verification round 4 is running; it also covers a regression the repair reported (a unit given in
  brackets after a single-letter name, read as amperes).
- Overseer rebuild: the eighth STEM repair finished its fixes and measurement; the independent audit follows.

### Progress, 00:00 UTC (24 October)

- Overseer rebuild: the eighth STEM repair measured 7149 tests passed, every recorded round unchanged, all 13 contained-run
  gates passing with no false alarm on genuine transfers, and 15/15 STEM mutations named. Its audit then found 4 issues
  (1 high: a false alarm on correct STEM working; 2 medium; 1 low), so the ninth STEM repair is running.
- Argument diagnostics: verification round 4 found 6 high-severity issues (round 3: 9); repair round 4 is running.

### Progress, 01:00 UTC (24 October)

- Overseer rebuild: the ninth STEM repair finished its fixes and is regenerating its schemas and docs; measurement and the
  independent audit follow.
- Argument diagnostics: repair round 4 restarted after a transient server error stopped it (its finished work is kept).
  Verification round 4 measured 44/44 development defects named with 0 false alarms and 65/66 hold-out defects named with
  1 false alarm (a two-way choice the task states word for word is refuted as the translator's own; being repaired).

### Progress, 02:00 UTC (24 October)

- Overseer rebuild: the ninth STEM repair measured 7235 tests passed, all 13 contained-run gates passing with no false alarm
  on genuine transfers, 15/15 STEM mutations named and 269/269 arena faults named; the independent audit is running.
- Argument diagnostics: repair round 4 is still running.

### Progress, 03:00 UTC (24 October)

- Overseer rebuild: the audit after the ninth STEM repair found 9 issues (none rated plainly high; 1 medium-high false alarm
  on correct physics working, 3 medium, 5 low or low-medium); the tenth STEM repair is running.
- Argument diagnostics: repair round 4 measured 8565 tests passed (round 3: 8249), 44/44 development defects named with 57/57
  controls clean, and 65/66 hold-out defects named with 67/68 controls clean. Verification round 5 is running.

### Progress, 04:00 UTC (24 October)

- Overseer rebuild: the tenth STEM repair has made its fixes, including the pack's STEM rules split into short paragraphs
  for the cheapest-tier agents; it is regenerating schemas and docs before measuring.
- Argument diagnostics: verification round 5 found new high-severity issues (adversarial 8, re-run findings 2, corpus 1;
  invariants none); the last allowed repair round is running. The fixed corpora still meet their gates (development 44/44
  with no false alarm; hold-out 65/66 with 1 false alarm).

### Progress, 05:00 UTC (24 October)

- Overseer rebuild: the tenth STEM repair measured 7343 tests passed; its independent audit is running. Severities the audit
  writes in between ("medium-high") now count as high for the loop and the commit gate.
- Argument diagnostics: the last allowed repair round is still running.

### Progress, 06:00 UTC (24 October)

- Overseer rebuild: the independent audit after the last measured repair (7343 tests passed, 13/13 contained gates) found
  1 high-severity issue (a unit conversion is flagged only when it is the last statement) and 4 medium; the last allowed
  repair round is running. The commit stays blocked while any high-severity issue is open.
- Argument diagnostics: the last allowed repair round is still running.

### Progress, 07:00 UTC (24 October)

- Overseer rebuild: the last allowed STEM repair round is still running.
- Argument diagnostics: the last repair round measured 8728 tests passed, 0 failed. In the final verification round the
  fixed corpora give development 44/44 named with 57/57 controls clean, and hold-out 65/66 named with 68/68 controls clean
  (no false alarm; the earlier one is gone). The adversarial and re-run reviews of this round are running.

### Progress, 08:00 UTC (24 October)

- Overseer rebuild: the last allowed STEM repair round is still running.
- Argument diagnostics: the repair loop ended after its last allowed round with high-severity issues still open (adversarial
  review 6, re-run findings 5, invariants 1; corpus none). The fixed corpora meet their gates: development 44/44 named with
  57/57 controls clean, hold-out 65/66 named with 68/68 controls clean. Nothing is committed. A closing round now compares
  every open issue with the committed code and fixes only the places where the changes are worse than it; the issues the
  committed code shares are recorded as known defects for round 8.

### Progress, 09:00 UTC (24 October)

- Overseer rebuild: the last allowed STEM repair round is still running.
- Argument diagnostics: every open issue was run on the committed code and on the changed code. Of the review issues, 6
  (plus 2 security issues) are places where the changes are worse than the committed code; 20 fail the same way on both
  and are kept as known defects for round 8. On the recorded rounds the changes give 403 better receipts and 29 worse ones,
  most of the worse ones coming from four causes (one error on a correct summary, three warnings). A fix round for those
  causes is running; nothing is committed.

### Progress, 10:00 UTC (24 October)

- Correction to the 09:00 note: the review issues where the argument-diagnostics changes are worse than the committed code
  number 7, not 6 (plus 2 security issues).
- Overseer rebuild: the last allowed STEM repair round measured 7583 tests passed (11 skipped, 4 expected failures that were
  already there), every recorded round unchanged (r7 177/177), and every contained gate passing (0 false alarms on genuine
  transfers, 269 of 269 faults named and confirmed, 15 of 15 STEM mutations). Its final independent audit is running.
- Argument diagnostics: the fix round for the regressions against the committed code is still running; nothing is committed.

### Progress, 11:00 UTC (24 October)

- Correction to the 06:00 to 10:00 notes: the overseer STEM repair rounds were numbered two too high. The round measured at
  7583 tests passed with every contained gate passing was the tenth repair, not the last. Its independent audit found 2
  high-severity issues (a correct whole-number rounded quotient written with '=' read as an error; a given value one unit
  off in its last digit accepted as matching), 4 medium and 1 low. The eleventh repair is running; at most one more repair
  and audit follow. The commit stays blocked while a high-severity issue is open.
- Argument diagnostics: the fix round closed all 16 places where the changes were worse than the committed code (3 of them
  by narrowing a new reading and giving up part of it). On the recorded rounds it adds no difference from the committed code.
  Development corpus: 44/44 defects named, 57/57 controls clean (committed code: 9 named, 41 false alarms). Hold-out
  corpus: 64/66 named, 68/68 controls clean (committed code: 13 named, 23 false alarms). Suite: 8847 passed; one timing test
  went over its 50 ms bound under load and passes when run alone. Independent differential and safety checks are running;
  nothing is committed.

### Progress, 12:00 UTC (24 October)

- Overseer rebuild: the eleventh STEM repair round is still running (at most one more repair and audit follow).
- Argument diagnostics: the independent checks of the first fix round confirmed the full suite (8848 passed when run alone)
  and equal functional counts with the committed code on every recorded round, and found 6 new high-severity places where
  the changes are worse than the committed code (2 from the safety review, among them a quotation reader that is quadratic in
  the number of quoted spans; 4 from the differential review), plus 3 medium. The second fix round is running; from now on a
  reading already narrowed once is reverted to the committed behaviour rather than narrowed again. Nothing is committed.

### Progress, 13:00 UTC (24 October)

- Overseer rebuild: the eleventh STEM repair round is still running.
- Argument diagnostics: the second fix round for the places where the changes are worse than the committed code is still
  running. Nothing is committed.

### Progress, 14:00 UTC (24 October)

- Overseer rebuild: the eleventh STEM repair round is still running.
- Argument diagnostics: the second fix round measured 8912 tests passed, 0 failed; development 44/44 named with 57/57
  controls clean and hold-out 64/66 named with 68/68 controls clean, both unchanged. It closed 6 places where the changes
  were worse than the committed code (4 by reverting a reading to the committed behaviour) and left 8. Three of those are
  cases the committed code catches only through false alarms that the changes removed, so it flags the matching correct
  answers too. The last fix round counts a committed-code detection only when the committed code tells the defect apart
  from its matching correct answer. Its verification is running; nothing is committed.

### Progress, 15:00 UTC (24 October)

- Overseer rebuild: the eleventh STEM repair round is still running.
- Argument diagnostics: the second verification found 7 more high-severity places where the changes are worse than the
  committed code. Two are speed: single answers of the latest recorded round take 11 to 13 times as long, and the round as a
  whole 3.1 times. The others are readings that turn a forecast, a supposition or a hedge in the task into a stated fact, or
  refute a plainly stated rule. The last fix round is running; nothing is committed.

### Progress, 16:00 UTC (24 October)

- Overseer rebuild: the eleventh STEM repair round is still running.
- Argument diagnostics: the last fix round for the places where the changes are worse than the committed code is still
  running. Nothing is committed.

### Progress, 17:00 UTC (24 October)

- Overseer rebuild: the eleventh STEM repair measured 7787 tests passed, every recorded round unchanged (r7 177/177) and
  every contained gate passing (0 false alarms on genuine transfers, 15 of 15 STEM mutations). Its audit found 1 high-severity
  issue (the STEM derivative check fixes the variable at the request's value, so it compares the derivative at one point only)
  and 3 medium. The twelfth and last allowed repair is running.
- Argument diagnostics: the last fix round measured 8946 tests passed, 0 failed, with both corpora unchanged (development
  44/44 named, 57/57 controls clean; hold-out 64/66, 68/68). It made the ledger readers linear, removed one more reading, and
  bumped the translator and rule versions. Four places remain where the changes are worse than the committed code (a hedge
  word elsewhere in a sentence refutes a plainly stated rule; relays carry a source's false finding; 'about 300' for 260 is
  held back; one answer group of the latest round takes about 11 times the committed code's time). The final independent
  check is running; nothing is committed.

### Progress, 18:00 UTC (24 October)

- Overseer rebuild: the twelfth and last allowed STEM repair round is running.
- Argument diagnostics: the regression closure ended after three fix rounds. Measured against the committed code: development
  corpus 0 false alarms with 44/44 defects named (committed code: 41 false alarms, 9 named); second hold-out set 11 false
  alarms (committed code: 31); recorded rounds unchanged; suite 8946 passed. Its last independent check still found six kinds
  of correct answer that now get a warning the committed code does not give, and one reading of space-grouped thousands whose
  time grows with the square of the input. A security round now makes every pattern the changes add linear, with outcomes
  kept identical. Nothing is committed.

### Progress, 19:00 UTC (24 October)

- Decision recorded: the overseer rebuild and the argument diagnostics are to be committed with their remaining open issues
  listed as known defects, and published through the usual simulated uploads; phase 2 then runs round 8.
- Overseer rebuild: the twelfth and last STEM repair round is in its documentation step; its measurement and the last
  independent audit follow.
- Argument diagnostics: a security round makes every reading the changes add linear in the input, keeping every outcome
  identical; independent checks follow, then the commit.
- Phase 2 is running again and waits for the overseer rebuild commit.

### Progress, 20:00 UTC (24 October)

- Overseer rebuild: the twelfth and last STEM repair round is still in its documentation step.
- Argument diagnostics: the security round is timing every reading the changes add on adversarial inputs at several sizes;
  independent checks and the commit follow.
- Phase 2 waits for the overseer rebuild commit.

### Progress, 21:00 UTC (24 October)

- Argument diagnostics: the security round made 17 readings that the changes add linear in their input. The worst of them
  took 28.7 s on a 20,000-character input and now takes 0.004 s; the space-grouped figure reading took 3.2 s on 16,000
  characters and now takes 0.07 s. Measured after the change: suite 9014 passed (68 new tests, each fix with an equality
  test against the old pattern and a growth test), both corpora identical case by case, every recorded round identical
  answer by answer. The independent outcome check passed; the independent security check is running. Nothing is committed.
- Overseer rebuild: the last STEM repair round is in its measurement step; the last independent audit follows.
- Phase 2 waits for the overseer rebuild commit.

### Progress, 22:00 UTC (24 October)

- Overseer rebuild: the twelfth and last STEM repair measured 7956 tests passed (11 skipped, 4 expected failures that were
  already there), every recorded round unchanged (r7 177/177) and every contained gate passing (0 false alarms on genuine
  transfers). Its last independent audit is running; the evaluation and the commit follow.
- Argument diagnostics: the independent outcome check of the security round found every outcome identical (suite 9014 passed,
  both corpora case by case, every recorded round answer by answer); the independent security check is running.
- Phase 2 waits for the overseer rebuild commit.

### Progress, 23:00 UTC (24 October)

- Overseer rebuild: committed on its build branch. Evaluation: suite 7956 passed (11 skipped, 4 expected failures that were
  already there), 358 of 358 tamperings detected, 0 false alarms on 138 genuine transfers, every contained gate passing, the
  knowledge pack exported. The last independent audit's 5 open issues (3 medium STEM readings not yet covered, 2 low) are
  recorded as known defects. Its upload waits: the upload gate requires every development test name, and one test was
  renamed when its assertion became stricter.
- Phase 2 is merging the overseer rebuild into the integrated line.
- Argument diagnostics: the second security round is running; an accuracy round follows for the false alarms on correct
  answers and three common STEM misses, then the commit.

### Progress, 00:00 UTC (25 October)

- Overseer rebuild: committed (suite 7956 passed, 358 of 358 tamperings detected, 0 false alarms on 138 genuine
  transfers). Its upload still waits on the test-name rule of the upload gate.
- Phase 2 is still merging the overseer rebuild into the integrated line.
- Argument diagnostics: the second security round is still fixing the five slow-pattern findings of the first round's
  review (the first round made 17 patterns linear; suite 9014 passed, corpus and arena outcomes unchanged). The accuracy
  round and the commit follow.

### Progress, 01:00 UTC (25 October)

- Phase 2 is merging the overseer rebuild into the integrated line: 46 conflicting places in 16 files resolved, keeping both
  sides' behaviour. The harness gives the same counts on the merge as on the development line (r1 30/30, r1-adv 150/151,
  r2 to r6 46/46 each, r7 177/177); the recorded rounds were not written (463 files checked). The last full run measured
  8241 passed and 2 failed outside the overseer, 2231 passed and 33 failed or errored in the overseer tests (mostly pack
  consistency checks after pack edits made during that run); the merge is being fixed and re-run before an independent
  verification decides whether it is committed.
- Argument diagnostics: the second security round is still in progress (the five slow-pattern findings now have fixes and
  tests; a sweep over every pattern is running).

### Progress, 02:00 UTC (25 October)

- Phase 2's merge of the overseer rebuild: the suite outside the overseer passes in full on the merge (8243 passed, 0
  failed, 45 deselected, 4 expected failures); the overseer tests and the contained overseer run on rounds r2 to r5 and r7
  are being re-run before an independent verification decides whether the merge is committed.
- Argument diagnostics: the second security round is taking its final timing measurements of the changed patterns.

### Progress, 03:00 UTC (25 October)

- Argument diagnostics: the second security round is done. Suite on the staged tree: 9058 passed, 0 failed (44 new
  security tests). 389 new or changed patterns were timed at three input sizes; the 74 that grew were each read at their
  call sites (2 fixed in this round, 1 removed, the rest read only on bounded windows, anchored at single places, or as
  slow in the committed code). An accuracy round has started on the false alarms on correct answers and three common STEM
  misses.
- Phase 2's merge of the overseer rebuild: suite on the merge 2271 passed in the overseer tests and 8243 passed elsewhere,
  0 failed; the contained overseer run passed 12 of its 13 gates, and the merge is being corrected for the remaining one
  (named STEM fault classes) and re-run before the independent verification.

### Progress, 14:00 UTC (25 October)

- The overseer rebuild is merged into the translator: suite on the merge 10503 passed, 0 failed; arena rounds r1 to r7
  at their recorded counts; the contained overseer run passed every gate.
- Argument diagnostics: two accuracy rounds are done and committed on their own branch. Suite 9191 passed; arena rounds
  unchanged; development corpus 44/44 defects named and 57/57 controls clean, hold-out corpus 64/66 named and 68/68
  controls clean. Known defects are listed in the commit and in docs/ARGUMENT_DIAGNOSTICS.md.
- The round 7 handoff findings are fixed on the merged tree: 5 blocking and 11 major findings; the minor findings are
  left as known defects and listed in the commit. Suite 10855 passed, 0 failed; arena rounds r1 to r7 at their recorded
  counts.
- Next: the delivery rule, the argument-diagnostics merge, integration, the gate, then arena round 8.

### Progress, 18:30 UTC (25 October)

- The round 7 handoff fixes are committed (suite 10855 passed, 0 failed; arena rounds r1 to r7 at their recorded counts).
- The delivery rule is committed: four minutes for the translator to give each claim a definitive outcome, otherwise the
  overseer agents' best validated output is delivered only above 90% accuracy, labelled overseer-selected. Suite 10944
  passed, 0 failed; arena rounds r1 to r7 at their recorded counts; the contained overseer run passed all 13 gates.
- Two test defects found by the pre-upload simulation are fixed in the same commit, neither in the product code: a race in
  two audit-replayer tests (4 of 40 repeated runs failed before the fix, 0 of 60 after), and a STEM probe compared with the
  wrong untampered copy (1 of 677 probes; all 677 pass after the fix, with the same outcomes as before round 7's changes).
- The argument-diagnostics build could not be merged: it was built on the code of 17 October, and both lines fixed the same
  findings differently. It stays on its own branch and will be rebuilt on the current code, keeping the current behaviour
  where the two disagree.

### Progress, 19:00 UTC (25 October)

- The argument diagnostics are being ported onto the integrated translator on their own branch, keeping the integrated
  behaviour wherever the two lines disagree; they are merged only after the full suite, the arena rounds, the contained
  overseer run and the three argument-diagnostics corpora pass on the port.

### Progress, 05:00 UTC (31 October)

- The argument diagnostics are ported onto the integrated translator and merged (9dec1e7). Independent verification on
  the port: 12,544 tests passed and none failed; every recorded arena round at its recorded count (r1 30/30, r1-adv
  150/151, r2-r6 46/46 each, r7 177/177); the overseer's contained run passed all 13 gates. The pre-upload simulation of
  exactly that code passed too (358 of 358 tamperings detected), and it is published on the main repository.
- Argument-diagnostics corpora on the port: development 44 of 44 defects named, 27 of 57 clean answers left clean;
  hold-out 61 of 66 named, 48 of 68 clean; second hold-out 68 of 70 named, 38 of 66 clean. Every clean answer still
  flagged is flagged by the integrated translator's own readings, with the same result as before the port.
- Integration step: the overseer now reads every code and diagnostic the translator emits (6ac78cc; 12,580 tests passed,
  none failed). Its knowledge pack 1.3 is restored to its released content and the changes ship as pack 1.4; the
  integration contract moves to 0.5 and documents the two new signed result fields.
- The integration gate (14 independent lenses) is running before arena round 8.

### Progress, 06:00 UTC (31 October)

- Integration gate, round 1: all 14 independent lenses on the integrated tree 6ac78cc have run or are finishing (12 of 14
  reported). They report 102 findings, 19 of them critical to the infrastructure: 12 text patterns whose running time
  grows with the square of the input (a 2,500-character answer can stall the hub; 10 were found in an earlier gate and
  still reproduce), 2 solver time-limit gaps (model extraction outside the timeout; full-timeout coverage probes after a
  counterexample), 2 combinator faults (duplicate STEM claim ids across two specialists; citations rewritten before the
  hub sees them), 1 delivery label (formally checked despite a STEM line not checked), 1 receipt gap (a verifier with no
  outcome leaves no trace) and 1 provenance gap (a relayed peer report relabelled as a primary source).
- Every finding goes to a fix round with a regression test per fix, then the full suite and every recorded round; round 2
  of the gate re-runs the lenses that found a critical issue. Arena round 8 starts only when no critical issue is left.

### Progress, 07:00 UTC (31 October)

- Integration gate, round 1, complete: all 14 lenses reported 115 findings, 21 of them critical to the infrastructure.
  (Correction to the 06:00 entry: the first 12 lenses had reported 103 findings, not 102.)
- The two critical findings added since 06:00 come from the fresh-session integration lens, which follows the
  integration kit's playbook in scratch clones: with the overseer attached to a channel, a request whose user input is
  not a string raises an error instead of being rejected with INT-REQ-009; and the overseer's receipt check runs the
  report-level hook a second time. The overseer-attached suite the playbook asks for measured 12,577 passed, 2 failed
  (those two), 13 skipped, in 63 minutes.
- The fix round for all 115 findings is running; the full suite and every recorded round follow before the commit.

### Progress, 18:00 UTC (31 October)

- Integration gate, round 1, fixed and committed (35f1be1): 101 of the 115 findings fixed, each with regression tests,
  including fixes for all 21 critical findings (the regular-expression blow-ups on long inputs, the solver time limits,
  the receipt left clean when a verifier returns no outcome, the relabelled peer report, the combinator citation rewrite,
  the colliding STEM claim ids, the delivery label and the overseer-attached request errors). Independent check of the
  committed tree: 13,157 tests passed, 12 skipped (round-dependent), none failed; every recorded arena round at its
  recorded count (r1 30/30, r1-adv 150/151, r2-r6 46/46 each, r7 177/177).
- Left as known defects, each needing a coordinated release rather than a gate fix: a new overseer pack for two new codes,
  the translator version bump that the signed kit vectors pin, a signature-scheme change, the overseer-audit key in the
  service, and a rebuild of the website patch set against the website's current main. The development corpus still flags
  25 of 57 clean answers (detection quality, not critical).
- Integration gate, round 2: the 7 lenses that reported a critical finding in round 1 are re-checking the committed tree.

### Progress, 19:00 UTC (31 October)

- Integration gate, round 2, on the committed round-1 fixes (35f1be1): six of the seven re-run lenses have reported.
  Solver robustness, STEM soundness and security found no critical issue (3, 14 and 3 lesser findings); their round-1
  critical findings are confirmed fixed. Three lenses found critical issues: parser safety 8 (further regular-expression
  blow-ups of the same kinds in other modules: request labels, chronology heads, English sentence ends, accuracy marks,
  code fences, ledger name partners and figure lists), correctness 1 (a new round-1 regression test depends on a 50 ms
  solver time limit and can fail on a loaded machine) and combinator faults 1 (a synthesis whose defaulted fields hold no
  value is not rejected at the hub). The fresh-session integration lens is still running.
- The round-2 fixes treat each blow-up as a class: every module in a fixer's paths is swept for the same kinds of pattern,
  with one hostile-input regression test per module.

### Progress, 20:00 UTC (31 October)

- Integration gate, round 2: six of seven lenses reported (11 critical findings in three lenses, listed at 19:00); the
  fresh-session integration lens is in its last step, the overseer-attached suite of the integration playbook. The
  round-2 fixes start when it reports.

### Progress, 06:00 UTC (1 November)

- Integration gate, round 2, fixed and committed (7f9ec18): 54 findings fixed, each with regression tests, including all
  10 critical findings. The regular-expression blow-ups were fixed as a class: every module in each fixer's paths was
  swept for the same kinds of pattern (adjacent unbounded runs around optional groups, scans to the end of the text from
  every unclosed opener, rescans per token or line), which fixed about 20 further instances and two parser crashes, and
  each swept module has a hostile-input regression test. The solver version is now pinned for fresh installs (a
  constraints file, the playbook step and the readiness check). Independent check of the committed tree: 13,697 tests
  passed, 12 skipped (round-dependent), none failed; every recorded arena round at its recorded count (r1 30/30, r1-adv
  150/151, r2-r6 46/46 each, r7 177/177).
- Integration gate, round 3: the 4 lenses that reported a critical finding in round 2 (parser safety, correctness,
  combinator faults, fresh-session integration) are re-checking the committed tree. Arena rounds 8, 9 and 10 follow
  when no critical finding is left.

### Progress, 07:00 UTC (1 November)

- Integration gate, round 3, on the committed round-2 fixes (7f9ec18): two of four lenses have reported. Parser safety
  found 6 issues, 2 of them critical (a ledger check that recomputes the figures of a source claim for every cited
  figure, and a figure pattern in the quantity reader with adjacent blank runs); the critical regular-expression findings
  have fallen from 12 in round 1 to 8 in round 2 and 2 now. Combinator faults found 10 issues, 1 critical (the hub runs
  its relay checks on the caller's synthesis object before re-validating it). Correctness and the fresh-session
  integration lens are still running. A round-3 fix round and a short round 4 follow.

### Progress, 18:00 UTC (1 November)

- Integration gate, round 3, is complete. Its 4 lenses reported 32 findings, 4 of them critical; the fixers' sweep for the
  same kinds of input stall found 2 more critical instances. 28 findings were fixed, including all 6 critical ones, and
  committed as 5c8577e after an independent verification: suite 16,141 passed, 12 skipped, 45 deselected, 0 failed;
  arena rounds r1 30/30, r1-adv 150/151, r2 to r6 46/46 each, r7 177/177.
- Integration gate, round 4, started at 17:02 on 5c8577e with the 3 lenses that had a critical finding in round 3. Parser
  safety reported 4 findings, none critical; correctness and combinator faults are still running. When no critical
  finding is left, the remaining findings are recorded as known defects and the pre-round-8 upload follows.

### Progress, 19:00 UTC (1 November)

- Integration gate, round 4, on 5c8577e: combinator faults reported 8 findings, none critical (missed detections in the
  synthesis ledger, such as a widened quantifier or a dropped attribution, and one laxer contract check in the arena
  harness). With parser safety's 4 findings, also none critical, two of the three lenses are clean of critical findings;
  the correctness lens is finishing its full suite run.

### Progress, 03:00 UTC (2 November)

- Integration gate, round 4, is complete. Its 3 lenses reported 17 findings, 1 of them critical: the integration claims
  took a check's verdict from the raw engine status and ignored its polarity, so checks whose sound answer is
  UNSATISFIABLE (Boolean identities in STEM working) came out inverted. 23 findings were fixed, including that one and
  further critical input stalls the fixers' sweep found in the synthesis ledger's readers, and committed as 1965f07 after
  an independent verification: suite 16,810 passed, 12 skipped, 45 deselected, 0 failed.
- Integration gate, round 5, started at 02:52 on 1965f07 with the correctness lens, the only lens that had a critical
  finding in round 4. When no critical finding is left, the pre-round-8 upload follows.

### Progress, 04:00 UTC (2 November)

- Integration gate, round 5, the gate's last round, is running on 1965f07 with the correctness lens. Besides re-checking
  round 4's findings and running the full suite, it builds a combined answer whose changed figure or invented quotation
  sits only past the synthesis ledger's new work bounds, and reports whether such an answer can reach a success status.

### Progress, 05:00 UTC (2 November)

- Integration gate, round 5, the last round, is complete: the correctness lens reported 2 findings, none critical, and
  the default suite on 1965f07 passed (16,810 passed, 12 skipped, 45 deselected, 0 failed). The gate is clean of critical
  findings after five rounds. Known defect carried forward (major, not critical): the synthesis ledger's new work bounds
  are spent in claim order, so a combined answer padded with harmless claims can leave a changed date or an invented
  quotation after the bound with only a warning; such an answer is released labelled "not verified" instead of being
  withheld.
- The pre-round-8 upload of 1965f07 started at 04:45 with its full simulation (suite and every recorded arena round).

### Progress, 08:00 UTC (2 November)

- The pre-round-8 upload of 1965f07 was held: its full simulation failed one contained-run gate,
  stem_fault_classes_named. From 35f1be1 (gate round 1) on, the STEM control probe units-translation-base-control, a
  correct conversion of 50.0 cm³ to 0.0000500 m³, was flagged as an introduced figure. The default suite runs neither
  the STEM probes nor the round-dependent tests without the recorded arena rounds, so the gate's own verification did
  not see it.
- Fixed at its cause in 6947c2d: the introduced-figure check and the part-of-claim and coverage readers now also read a
  stated figure in its coherent SI unit and in its unit without the prefix, with exact factors from the STEM unit table;
  wrong factors stay flagged. Verification: suite 16,864 passed, 12 skipped, 45 deselected, 0 failed; the five
  round-dependent test files with the recorded rounds, 151 passed; STEM probes on round 7, 677 of 677 with the gate ok;
  harness r7 177/177. The full publisher simulation of 6947c2d runs before its upload.
- Arena round 8 is running: the translators, the combinator and the harness step are done, and the overseer steps are
  in progress.

### Progress, 09:00 UTC (2 November)

- The publisher held 6947c2d at 08:01: its commit message gives the verification in prose, not in the harness and suite
  lines the publisher reads. 16d5a4a records the contained-run finding, its fix and the measurements on 6947c2d's tree in
  docs/STEM_RESULTS.md section 10.14, with those lines; it changes documentation only, so the code is that of 6947c2d.
  The publisher's full simulation of 16d5a4a runs before its upload.
- Arena round 8: the translators, the combinator, the harness step and the overseer preparation are done; the overseer
  lenses are running.

### Progress, 10:00 UTC (2 November)

- The publisher's full simulation of 16d5a4a (the code of 6947c2d): the suite with the recorded rounds gave 16,876
  passed, 45 deselected, 0 failed, and the harness on round 7 gave 177 of 177; the contained run on the recorded rounds
  is in progress. The upload follows only if every gate passes.
- Arena round 8: the overseer lenses are running.

### Progress, 03:00 UTC (7 November)

- Arena round 8 (integrated round c1): the fixes are verified and committed ("Fix the c1 clearance findings"): the suite
  gave 18,395 passed, 12 skipped, 0 failed, and the harness gave r1 30/30, r1-adv 150/151, r2 to r6 46/46 each, r7 177/177
  and c1 203/203, with no drop. The prototype documentation is committed ("Prototype: integrated translator after round 8").
- The independent push check held the round-8 upload: one critical item is open (a note in an answer's meta-text that
  asserts the answer is sound could still lift the formally checked label). Its fix is in progress; nothing from round 8
  is uploaded until a new independent check passes.

### Progress, 04:00 UTC (7 November)

- The fix for the push check's open critical item: the first version passed its own 364 targeted tests, but an
  independent attack freed 196 of 244 assurance paragraphs written as source or fidelity notes, so it was not accepted.
  A narrower rule (only study suggestions, first-person access limits and statements that a named part is not checked
  are notes) is being written and will be attacked again. Nothing from round 8 is uploaded until a new independent push
  check passes.

### Progress, 05:00 UTC (7 November)

- The narrower rule for the push check's open critical item: on 5,508 generated source and fidelity notes it frees none
  (the held version freed 1,116), and its 1,047 targeted tests pass. It refuses 45 of 47 recorded genuine notes, so three
  recorded English answers now also name their note as a self-report; every delivery decision keeps its mode, label and
  delivered flag. A second independent attack on it is running.

### Progress, 06:00 UTC (7 November)

- Second independent attack on the narrower rule: the rule itself held (one lens tried 40,000 inputs with no bypass and
  no regression; 238 attack paragraphs reached the rule and none was freed). The remaining bypasses travel outside it,
  through how answers are split into blocks: a one-line "Sources:" block (introduced by the round-8 citation change) and
  a note-led block whose later sentence is not a note (present before round 8). Both are being closed in the delivery
  decision itself, without changing the parser. Nothing from round 8 is uploaded until a new independent push check
  passes.

### Progress, 07:00 UTC (7 November)

- The fix now also reads every answer's text for blocks opened by a note or sources lead, including leads the parser
  reads as body or as a source list; such a block must be read positively as a note or as a plain source list, or the
  answer is refused the formally checked label. Its targeted tests pass (295 for the new reader, 1,047 for the note
  rule). On the 24 recorded round-8 answers every delivery keeps its mode and label; the genuine closing lines of 16 of
  18 recorded answers are now refused as well, so the label is rarely reachable until those readers are widened under
  attack. The third and last independent attack round is running.

### Progress, 08:00 UTC (7 November)

- The third independent attack round on the fix still found bypasses (85, 9 and 12 across its three lenses), all through
  leads or labels outside a closed list (unlisted note-like leads, invisible characters inside a lead, list prefixes,
  layout labels). A fourth fix round inverts the rule: every sentence the parser does not treat as a material claim must
  be read positively as a note, a plain source list or a bare layout label, after the text is normalised, or the answer
  is refused the formally checked label. A fourth attack round follows. Nothing from round 8 is uploaded yet.

### Progress, 09:00 UTC (7 November)

- The fourth fix round (the inverted rule: every sentence the parser does not treat as a material claim must be read
  positively, after normalisation, or the answer is refused the formally checked label) is still being written and
  tested; a fourth independent attack round follows it. Nothing from round 8 is uploaded yet.

### Progress, 10:00 UTC (7 November)

- Fourth independent attack round on the fix: the inverted rule closed the lead and label channels; two lenses found
  flaws in the fix's own new readers (an open part-label slot after STEM layout labels such as "Working (fine):", and a
  source-list reader that accepts words naming no source), which a short fifth fix round closes. Assurances that a
  branch's parser reads as claims of the answer (for example "All good." after a physics result) still pass; that gap
  predates round 8 and is scheduled for round 9. Nothing from round 8 is uploaded yet.

### Progress, 11:00 UTC (7 November)

- The fifth fix round (closing the flaws the fourth attack found in the fix's own readers: the open part-label slot
  after STEM layout labels, source-list words that name no source, and look-alike letters in leads) is running; a scoped
  fifth attack round follows it. Nothing from round 8 is uploaded yet.

### Progress, 12:00 UTC (7 November)

- Fifth independent attack round on the fix, scoped to compare with the published base: assurances that a branch's
  parser reads as claims of the answer reach the formally checked label on answers the published base withheld (219
  inputs on one recorded English answer that carries a note, and the physics text path), so they are a regression of
  round 8, not only an older gap; and one reader of the fix skipped symbols written before a "Sources:" lead. A sixth fix
  round closes both: the label now requires every claim of the answer to carry a successful signed formal result, and
  every lead reader reads the whole block. A sixth attack round follows. Nothing from round 8 is uploaded yet.

### Progress, 13:00 UTC (7 November)

- The sixth fix round is running: the formally checked label will require every claim of the answer to carry a
  successful signed formal result, and every lead reader reads the whole block. A sixth independent attack round, which
  also compares each input with the published base, follows it. Nothing from round 8 is uploaded yet.

### Progress, 14:00 UTC (7 November)

- The sixth fix round is still running (the formally checked label to require a successful signed formal result for
  every claim; earlier tests that pinned the weaker behaviour are being rewritten to the stricter rule, none deleted).
  A sixth independent attack round follows it. Nothing from round 8 is uploaded yet.

### Progress, 15:00 UTC (7 November)

- Sixth independent attack round on the fix: the stricter label rule (every claim needs a successful signed formal
  result) holds against the claim channel the fifth round found, but text still reaches the formally checked label
  through words written into a verified claim, self-grades the verifier itself confirms, visible combining letters and
  hidden format characters. The round-8 release will therefore withhold the formally checked label for every answer
  (every answer follows the existing fallback path) until a label policy holds under attack; the readers built in this
  fix stay in place for that work. Nothing from round 8 is uploaded yet.

### Progress, 16:00 UTC (7 November)

- Sixth fix round finished: a new refusal-only rule withholds the formally checked label for every answer until a
  label policy holds under attack (26 files changed in the fix tree; targeted runs include 55, 92 and 87 passing tests
  in the delivery-policy, gate and clearance files). Replaying the 24 recorded round-8 deliveries changed only the
  label and its reason. A seventh independent attack round is checking that nothing reaches the label and nothing else
  changed. Nothing from round 8 is uploaded yet.

### Progress, 20:00 UTC (7 November)

- The follow-up fix 32a5c0e ("Fix the c1 clearance findings") is committed: the full suite gave 22,503 passed, 12 skipped,
  45 deselected and 0 failed; the harness is unchanged on every recorded round (r1 30/30, r1-adv 150/151, r2 to r6 46/46,
  r7 177/177, c1 203/203); the 24 recorded round-8 deliveries are all withheld, as before. Its independent push check holds
  nothing and states that it resolves the hold on f2329df. Nothing from round 8 is uploaded yet.
- Corrections to the commit message of 32a5c0e: "every rule can only remove the label" holds against f2329df, not against the
  published base 16d5a4a (the closed note allowlist frees some notes the base blocked, and when a refusal rule raises, the
  fallback now decides the mode instead of withholding the answer); the five end-to-end tests accept a reason from any of the
  rules they name, not only the one rule; the renamed tests keep their cases against the landing, while against the parent
  commit their assertions changed to the withheld label. With no overseer agents configured, every answer is withheld.

### Progress, 21:40 UTC (7 November): the overseer connected, then made a sub-project (architecture step 2, not committed)

- The overseer port is connected to the rebuilt overseer: its embedded adapter `epinoic_overseer.port` is the service's
  default overseer port, the service pins the overseer's knowledge pack (`overseer_port.PINNED_PACK_DIGESTS`; another
  pack is refused with `KIT-HS-007`), and `tests/integration/test_turn_checker.py`, `test_turn_review.py` and
  `test_turn_fixes.py` run on both the test double and the adapter. The overseer then moved into the sub-project
  `overseer/` (package `epinoic_overseer` 1.0.0, its own `pyproject.toml`, README, docs, tests and harness); it imports
  the translator only through `epinoic_logic.api` (`docs/PUBLIC_API.md`) and `epinoic_logic.integration`, the
  translator never imports it, and nothing stays at the old path.
- Measured against a record taken on 32a5c0e before the move: the 96 moved overseer test files keep their counts (4,904
  assertions, 1,533 test functions, 188 `pytest.raises`/`warns`); every pack digest and the exported zip are unchanged;
  the planner is identical on all 268 recorded channels of r2 to r5 and r7; the harness is unchanged on every recorded
  round (r1 30/30, r1-adv 150/151, r2 to r6 46/46, r7 177/177, c1 203/203); the contained run, now run from `overseer/`,
  is identical to the base commit's (12 of 14 gates PASS; `tamper_suite` and `stem_fault_classes_named` FAIL on the base
  commit too, `overseer/docs/OVERSEER_RESULTS.md` section 36).
- The simulation without its test double (a fresh patched export of website base M, the runtime copy and the agents
  copy): five gates PASS, G-FAULT FAIL on the 12 warning-level cases (decision D34, open), G-EQ-CONTAINED and G-OVS not
  collected by the simulation yet.
- Tests rewritten to the connected state, each keeping or adding assertions: the simulation on this tree
  (`test_sim_gates.py`: the service now starts, so the gates name the missing copies and the service's start is
  asserted), the readiness check's import path (`test_readiness.py`: the overseer's `src/` added), the package data of
  the pack (`overseer/tests/overseer_tests/test_knowledge_drift.py`: read from the sub-project's `pyproject.toml`).
- `python -m pytest -q` at the repository root (both suites, one session): 22,601 passed, 12 skipped (the recorded rounds
  are not in the repository), 45 deselected, 0 failed, in 1 h 20 min. The overseer's suite run alone from a split copy of
  the sub-project: 7,055 passed, 12 skipped.

### Progress, 00:57 UTC (8 November): the flash router carries the pool's planning decision (architecture step 2c, not committed)

- The overseer pool's planning decision (which instances review which dossiers, and which go to independent duplicates)
  moved into the flash router, `flash-router/` (`epinoic-flash-router` 0.2.0; not the translator's `RouterHub`): its rules
  and cost data are versioned data files with digests (`src/epinoic_flash_router/data/`, the 0.1.0 files kept at their
  digests), it has a runner (`python -m epinoic_flash_router_cli`) and its own docs and tests, and it is reached through
  the router port's new pool operation (`router_pool.py`, PROTOCOL.md section 7b, pool port 1.1). The overseer pool
  attaches it by capability (`OverseerPool(..., router=)`, `DeliveryPolicy(router=)`), never imports it, and keeps the
  floor (`epinoic_overseer.floor`, `minimum-oversight-floor/pool-1`): a plan below it is refused (`KIT-RT-020`, recorded
  in the plan's admission and the signed audit) and the floor plan runs; with no router the floor plan runs.
- With the router attached, all 278 recorded plans of r2 to r5 and r7 (268 channels, 10 batches) are reproduced exactly;
  the harness on every recorded round and the contained run are unchanged (12 of 14 gates PASS, the same two FAIL as on
  the base commit); `git subtree split --prefix flash-router` on a disposable clone gives the directory's tree, whose
  suite passes standalone (52 passed).
- Tests changed, none weakened: five tests that pin the planner's decision (`test_consolidation_pool.py`,
  `test_integration_codes.py`) attach the router and assert the plan is the router's; the root `testpaths` pin
  (`tests/integration/test_overseer_subproject.py`) lists the three suites; the router's conformance suite moved into its
  test package (`flash-router/tests/flash_router_tests/`).
- `python -m pytest -q` at the repository root (three suites, one session): 22,689 passed, 12 skipped, 45 deselected,
  0 failed, in 1 h 14 min.

### Progress, 04:00 UTC (8 November)

- The simulation of 32a5c0e found three regressions of the round-8 fixes that every earlier run had skipped (they need the
  recorded rounds or the contained run): a stale round-7 overseer test, a declined answer's word count accepted without a
  recount, and figures traced through values the task never writes. Commit 5060a52 fixes them on the sub-project layout of
  ab44c8a. With the recorded rounds supplied the full suite gave 22,721 passed, 0 failed and 0 skipped; the contained run
  passed all 14 gates (355 of 355 tamperings, all 677 STEM probes named); the harness is unchanged on every recorded round.
  Its push check and the upload simulation are running. Nothing from round 8 is uploaded yet.
