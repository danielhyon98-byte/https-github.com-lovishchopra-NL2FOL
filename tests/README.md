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
