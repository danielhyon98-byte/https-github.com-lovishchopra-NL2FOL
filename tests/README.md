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
