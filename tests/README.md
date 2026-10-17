# Bug testing and stress testing: results

This file reports how the translator infrastructure is tested and what the tests have
found so far. The infrastructure is code, not an agent. It converts the English outputs of
specialist sub-agents into logical code (an IR the Z3 engine decides) so that no
miscommunication passes between the router, the subject specialists and the combinator.

Every figure below was measured on the code at the commit named. This file is updated after
each round. Last update: after the round-4 fix round (commit `a2d874d`), with the round-5
overseer verdicts that had arrived.

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
   forwarded by the router to the other specialist, who quotes it.

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
