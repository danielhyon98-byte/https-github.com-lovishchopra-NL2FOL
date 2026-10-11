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

Service-level load (concurrent HTTP clients, rate limiting, semaphore) is measured
in the clearance-gate iterations once the service exists; see `docs/STATUS.md`.
