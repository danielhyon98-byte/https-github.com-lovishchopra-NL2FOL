# Volatile fields of the G-EQ comparison

The G-EQ-ARENA gate compares, for every corpus item, the website-path call's evidence and the reference harness's
genuine pass on: the receipt status, the multiset of finding codes, the per-claim display statuses, the problem,
configuration, limits and binding digests of every result, the branch formal checks, and the sets of served and
unserved fixtures (`compare.py`, `GATED_FIELDS`). These fields are excluded, each for the reason given:

| Field | Why it differs between two runs of the same item |
|---|---|
| `receipt_id`, `message_id`, `outcome_id`, `translation_id`, `result_id` | minted per transfer or per result (random) |
| `request_id`, `task_id`, `report_id`, `channel` | the website path uses the website's turn and attempt ids and `rep_<turn>_<agent>_v<n>`; the arena uses `req-<item>`, `<item>` and `rep-<item>-<variant>` |
| `problem.request_id` inside each encoded problem | the fixture provider serves a fixture under the request id of the claim it translates; G-EQ hashes the problem with this id normalised (`compare.result_digests`), so every other byte still counts |
| `created_at`, `issued_at` | wall-clock time |
| `signature`, `key_id` | the service's ephemeral keys differ from the arena's fixed test key; the binding digest does not include either |
| `latency_ms`, `timings` | measured time |
| `summary` | free text built from the same fields that are compared |
| `smt2` | the exact SMT-LIB text carries the problem's ids |
| `versions_digest` | equal by construction when both sides run the same tree; it enters the recomputed binding digest, so a difference still fails the gate |
