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
