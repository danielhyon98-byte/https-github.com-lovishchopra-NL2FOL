# Stress results

Layer 3 measurements from `tests/stress/` (run with `pytest -m stress tests/stress`).
Numbers are from this development container (4 CPUs) and are regression guards, not
capacity claims. Raw JSON is in `tests/stress/results/`.

## Iteration 1 — engine (2026-10-11)

| Scenario | Result |
| --- | --- |
| 1000 sequential entailment verifications | 219.5/s; p50 4.4 ms, p95 5.7 ms, p99 6.4 ms, max 7.0 ms; all ENTAILED; RSS growth 0.06 MB (no context leak) |
| 240 problems, 16 threads vs sequential | statuses and binding digests identical; 160 ENTAILED / 80 COUNTEREXAMPLE |
| 12 adversarial payload types × 20 rounds (depth bombs to 10,000, 5000-ary conjunction, unknown op, 5000-digit numeral, Bool/Int confusion, non-constant divisor, invalid UTF-8, 200,000 open brackets, 1.1 MB body, 5000 premises) | 220 INVALID_FORMALIZATION, 20 UNSUPPORTED, 0 INTERNAL_ERROR; worst 71 ms |
| 16 concurrent hard nonlinear problems, 100 ms timeout | all TIMEOUT; worst wall 523 ms |
| 45 s mixed soak | 10,201 verifications; 0 INTERNAL_ERROR; RSS growth 0.02 MB |

## Iteration 1 — translator channel and integrity cross-checks (2026-10-11)

| Scenario | Result |
| --- | --- |
| 300 router→specialist→router cycles on one channel (request parsing, envelope, scope, quotation grounding, two constraints decided by the engine as signed results) | p50 4.6 ms, p95 6.4 ms, p99 7.0 ms per cycle; all ACCEPTED; RSS growth 6.7 MB (in-memory message log and receipts retained by design) |
| 16 threads, one channel each, 40 cycles | 640/640 cycles accepted with all constraints satisfied |
| 8 specialists × 15 requests accumulating 120 formalized claims with a cross-agent consistency check on every response; the last claim contradicts the shared value | conflict named on the final receipt: True; undecided: False; p50 58 ms, p95 97 ms, final response 88 ms |
| 200 adversarial responses (unselected agent, overlong, invented quotation, out-of-scope document, unknown request) | 120 REJECTED and not delivered, 80 delivered with findings, 0 crashes |

Observation: per-response cost grows with the number of accumulated formalized
claims because every response re-runs the joint consistency check; at 120 claims it
is still well under the solver timeout. Incremental or pairwise checking is the next
optimization if a task accumulates many hundreds of claims.

## Iteration 1 — branching hub (2026-10-11)

Five subject branches on one hub, 100 router→specialist→router cycles each (500 transmissions), every
cycle running the branch's integrity pack and the report's own arithmetic and chronology checks through
the engine (700 formal checks decided, all holding for the genuine texts).

| Branch | p50 ms per cycle | p95 ms per cycle |
| --- | --- | --- |
| History | 11.5 | 15.9 |
| Economics | 11.4 | 14.9 |
| Business Management | 11.1 | 14.5 |
| Psychology | 5.9 | 7.5 |
| English A: Literature | 0.8 | 1.1 |

Statuses: {'ACCEPTED_WITH_FINDINGS': 400, 'ACCEPTED': 100}; RSS growth 42.2 MB over 500 cycles (per-task channels retain
their message logs and receipts by design).

Adversarial numeric text (300 texts: 60-digit numerals, 400 random figures in one sentence, 50 repeated
from/to clauses, zero denominators, overflow-like literals): 3150 formal checks produced,
0 internal errors, worst text 387 ms.

Service-level load (concurrent HTTP clients, rate limiting, semaphore) is measured
in the clearance-gate iterations once the service exists; see `docs/STATUS.md`.

## Iteration 2: arena stress (real agent outputs replayed under load)

Replays of the six round-2 specialist outputs (including the History-to-English peer exchange)
through the hub, `scripts/arena/stress_arena.py <round> 30`:

| Leg | Result |
| --- | --- |
| Sequential, 180 transmissions | p50 18.6 ms, p95 26.7 ms, p99 33.8 ms; 56.6 transmissions/s; 60 ACCEPTED, 120 ACCEPTED_WITH_FINDINGS; RSS growth 27.9 MB (receipts and ledger retained by design) |
| 16 threads, one hub each, 672 transmissions | 0 REJECTED; statuses identical in kind to the sequential run |
| Service, 400 concurrent verify requests, admission bounded at 4 | 4 served, 396 shed with 503 and Retry-After (load shedding by design, not failures) |

Finding and fix. Raising the service's admission bound to 64 made the same run **segfault**:
`SolverConfig.memory_max_mb` is the budget of one verification, but Z3's `memory_max_size`
is process-global, so 32 concurrent verifications under the 512 MB default exhausted it
together, Z3 aborted and the next solver call crashed the process (reproduced engine-only:
32 threads x 512 MB crash, 16 x 512 and 32 x 1024 pass). The engine now counts active
verifications and applies budget x active, only raises the limit while anything runs,
returns to the single budget when idle, and after a memory abort restores no less than the
running need. A stress-marked subprocess test (`tests/engine/test_memory_budget.py`) runs 32
concurrent verifications under the default budget; the unit tests cover the arithmetic.
The stress-marked suite (`pytest -m stress`, 12 tests) passes after the fix.

## Iteration 3: arena stress re-run after the round-2 fix round

The same six round-2 outputs replayed through the hub after the round-2 fixes
(`scripts/arena/stress_arena.py r2 30`, run alone on the container):

| Leg | Result |
| --- | --- |
| Sequential, 180 transmissions | p50 37.3 ms, p95 75.5 ms, p99 98.7 ms; 24.7 transmissions/s; 90 ACCEPTED, 90 ACCEPTED_WITH_FINDINGS; 0 crashes; RSS growth 27.8 MB (receipts and ledger retained by design) |
| 16 threads, one hub each, 672 transmissions | 0 REJECTED, 0 crashes; 336 ACCEPTED, 336 ACCEPTED_WITH_FINDINGS; wall 54.2 s |
| Service, 400 concurrent verify requests under the admission bound of 64 the harness sets | 400 served with 200, 0 shed; wall 12.5 s (after the memory-budget fix of iteration 2, 64 concurrent verifications no longer exhaust the process-global solver limit) |

Two changes from iteration 2. The statuses moved from 60/120 to 90/90: three of the six
outputs now cross with no finding (the History peer paragraph with an information-level
HI-STR-003 only, the History crash paragraph, and the peer-dependent English paragraph
whose false ES-SRC-003 is gone); the remaining findings are the English answers' four
blank-line blocks against "one analytical paragraph" (INT-REQ-005) and the famine
paragraph's quotation with no text to check it against (CORE-SRC-003), both genuine
properties of the outputs. The per-cycle cost rose from p50 18.6 ms
to 37.3 ms: a profile of 30 cycles puts most of the increase in quotation location
(`translate/grounding.locate_quotation` via `adapters/sources.check_excerpt`, about 1,500
calls), because the English parser's attribution step and the new attribution checks now
locate every excerpt in every supplied text and the normalised document text is rebuilt
for each excerpt. Caching the normalised document per supplied text is the next
optimisation; the engine's own share (90 bound checks, 0.7 s of 2.3 s profiled) is
unchanged.

Crash counting. The adversarial overseer found that one input that made the hub raise
aborted the whole run before `stress.json` was written. `one_cycle` now runs every hub call
(open_task, dispatch, receive) under try/except: a raising input is counted under the status
`CRASH:<ExceptionType>` (and a rejected request under `REQUEST_REJECTED`), the `crashes`
count is reported for the sequential and threaded legs, the run continues, and the script
prints where `stress.json` was written. Verified by injecting a raising `receive`: the cycle
returns `CRASH:RuntimeError` and the next cycle runs. The input the overseer used (about 600
arithmetic sentences, which overflowed the receipt summary) no longer raises after the
channel's summary fix, so this run counts 0 crashes.
