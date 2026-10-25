# Signed results from earlier releases (upgrade tests)

These files are genuine engine output, signed by earlier releases, kept so the upgrade tests
(`tests/engine/test_review_engine_fixes.py`) consume real results of a previous build instead
of results signed and checked by the same build.

| File | Produced by | Signing key (public test constant) |
| --- | --- | --- |
| `release_0_3_0_signed_results.json` | engine 0.3.0, policy 2026.10-v3 (the STEM merge, commit `83e97e9`), before the review fixes | `upgrade-test-key-0123456789abcdef`, key id `upgrade` |
| `release_0_2_0_baseline_signed_result.json` | engine 0.2.0, policy 2026.10-v2 (the published baseline `650d1d3`), reproduced by the external review of 12 October 2026 | `probe-signing-key-0123456789012345`, key id `probe` |
| `release_0_4_0_signed_results.json` | engine 0.4.0, policy 2026.10-v4 (the review-fix release `22d6a5b`), before the argument diagnosis | `upgrade-test-key-0123456789abcdef`, key id `upgrade` |

`release_0_3_0_signed_results.json` maps a case name to the problem, the solver configuration,
the limits and the signed result. The cases are the review's reproductions: an assumption that
restates the conclusion (`p |= p`), a premise-free tautology run with `produce_unsat_core=false`
(signed `ENTAILED` without `E108` by 0.3.0), a chain resting on model-labelled `arithmetic_fact`
premises (no dependency listed by 0.3.0), `x*x = 4` under permissive limits (bound exactly like a
default run by 0.3.0) and a definition-only counterexample (`E110` by 0.3.0).

`release_0_4_0_signed_results.json` has the same shape. Its cases (an argument whose premises a check established, and
one that rests on the writer's own link) carry no `argument_rules` and no `named_diagnostics`: the contract tests of the
argument diagnosis (`tests/contract/test_result_fields.py`) check that such a result still parses, re-serialises
byte-identically and keeps a valid signature, and that it is never current: it is stale through its identity, and the
release check also refuses it because its argument diagnosis was not computed.

The keys are deliberately public local test constants, never production credentials. Do not
regenerate these files with the current build: their value is that an earlier build signed them.
