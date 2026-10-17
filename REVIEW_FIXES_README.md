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
