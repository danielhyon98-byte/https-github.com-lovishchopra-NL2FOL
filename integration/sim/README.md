# Integration simulation (`integration/sim/`)

The local end-to-end simulation of protocol `epinoic.integration.v1` through the website path (PROTOCOL.md section 14.5;
playbook step 12). It runs on loopback only, with the fixture provider, ephemeral keys and synthetic data. No
provider is called, nothing is deployed, and no repository is written to: the corpus and any supplied rounds are
copied first.

```
python integration/sim/run_sim.py --website <disposable export> --agents <agents copy> --translator <kit> \
    --corpus integration/sim/corpus --out <dir> [--rounds <dir>]
```

`<dir>/summary.md` has one line per gate (PASS, FAIL or NOT RUN with its reason); `<dir>/results.json` has the
denominators, the case ids, what was not run and why, and the sub-checks. Exit status 0 only when no gate FAILs and
all eight gates PASS.

## Parts

| File | Role |
|---|---|
| `run_sim.py` | orchestrates the steps below, then the gates |
| `gates.py` | the eight gates as pure functions of the records; the NOT RUN rule |
| `compare.py` | the G-EQ projection of a receipt and of an arena record, field by field (`VOLATILE.md`) |
| `reference.py` | `run_arena.run_round` on a copy of the corpus (and `run_contained.py` when the overseer is on the tree) |
| `fixture_verifier.py` | the arena's fixture-serving rule as the service applies it; parity-tested against `run_arena` |
| `faults.py` | the arena's own mutations and the STEM mutations, applied by the arena's own functions |
| `tamper_web.py` | the website-path tampering cases W-T1 to W-T8 (and an adapter-level sub-check) |
| `website-driver.mjs` | replays `users.json` through a disposable website export with the verified backend |
| `agents-driver.mjs` | the agents router, the offline runtime and the specialist port, without the website |
| `users.json` | 26 simulated users, sessions of one to four turns, each turn naming a corpus item and an action |
| `corpus/synthetic/s1/` | the synthetic corpus in the arena round format (`integration/tools/build_corpus.py`) |
| `corpus/DATA-TERMS.md`, `corpus/MANIFEST.sha256` | the corpus's terms and digests |

## What runs on the pre-build tree, and what is connected in phase 2

On the pre-build branch the overseer package, the named-policy allowlist of contract 0.3 and the combinator are not
on the tree, so the checks service refuses to start (`KIT-HS-006 named_policies_unavailable`, then
`KIT-HS-007 overseer_unavailable` once 0.3 is merged). `run_sim.py` reports that as the reason, and every gate is
NOT RUN, never PASS: the exit status is 1. What does run here:

- the reference harness on a copy of the synthetic corpus (sub-check `arena:s1`: every genuine and mutation record
  functional, the round not qualified);
- the fault cases are built by the arena's own functions (sub-check `fault_cases`);
- the tampering cases through the Worker's release-gate module alone (sub-check `tamper_adapter`: W-T1 to W-T8
  refused with their codes). This is evidence about one module, never the gate, which needs the whole website path.

Connected in phase 2 (recorded in the pre-build notes for phase 2):

1. the website path: patch set M applied to the disposable export (`integration/website/apply.mjs`), the driver's
   replay loop over `users.json` with `options.verified.inner` = the simulation's specialist orchestrator over the
   agents copy's offline runtime (`createOfflineTestRuntime`, the synthetic bundle, an `authorizedGenerate` that
   returns each item's recorded answer);
2. the agents driver's STEM, duplicate, clarify and (with the combinator) combined turns;
3. the website projections from the evidence tap for G-EQ-ARENA (the response receipt of each call, projected by
   `compare.receipt_projection` with the item's fixture ids), the fault replay for G-FAULT, the invariants for G-INV,
   the displayed labels for G-HON, the verdicts for G-DEL, the handler-level tampering for G-TAMPER;
4. the contained run for G-EQ-CONTAINED and the probe providers through the asynchronous review for G-OVS.

## Which gates have material on the synthetic corpus

Established at kit build (the NOT RUN rule): G-EQ-ARENA, G-FAULT, G-INV, G-HON, G-DEL and G-TAMPER have material on
the synthetic corpus once the website path exists. G-EQ-CONTAINED and G-OVS need the overseer's contained run. Without
`corpus/licensed/` (decision D15), these are NOT RUN on the synthetic corpus: the re-keyed pass, the adjudicated genuine
faults, the recorded overseer reports and any real cheapest-tier translation.

## Request ids and digests

A website-path call's request id is the website's attempt id; the arena's is `req-<item>`. The fixture provider serves
each fixture under the request id of the claim it translates (`RekeyingFixtureProvider`; a no-op in the arena), so the
encoded problems differ only by that id. G-EQ compares the problem and binding digests with the problem's request id
normalised (`compare.result_digests`): every other byte of the problem, the configuration, the versions and the limits
still count (`tests/integration/test_fixture_parity.py` shows the normalised digests equal on both paths).
