# Integration simulation (`integration/sim/`)

The local end-to-end simulation of protocol `epinoic.integration.v1` through the website path (PROTOCOL.md section 14.5;
playbook step 12). It runs on loopback only, with the fixture provider, ephemeral keys and synthetic data. No
provider is called, nothing is deployed, and no repository is written to: the corpus and any supplied rounds are
copied first.

```
python integration/sim/run_sim.py --website <disposable export> --specialist <runtime copy> --agents <harness copy> \
    --translator <kit> --corpus integration/sim/corpus --out <dir> [--rounds <dir>]
```

`<dir>/summary.md` has one line per gate (PASS, FAIL or NOT RUN with its reason); `<dir>/results.json` has the
denominators, the case ids, what was not run and why, and the sub-checks. Both name the copy each path was given, and a
path that did not run says so (below, "The two copies"). Exit status 0 only when no gate FAILs and all eight gates PASS.

## The two copies

The simulation runs two archive copies of the agents repositories (`git archive` with `.kit-archive-commit`; playbook
step 8), by role (`COMPATIBILITY.json` `repositories`, pins in `agents_pins`):

- `--specialist`: the runtime the **website path** runs, the retrained repository at the runtime pin
  (`agents_pins.runtime`: runtime 0.2.0, contract `epinoic.specialist-runtime.v0.2.0`, the History knowledge base of
  `agents_pins.knowledge_bases`). It is the runtime the website path is to deploy (the deployable runtime pin); the
  website's History pull requests, unmerged, vendor runtime copies that playbook step 9a compares with this pin, and the
  kit deploys nothing.
- `--agents`: the **harness** (`repositories.agents_harness`, at its pin or, in a session, at origin's default branch):
  runtime 0.1.0 and its router in one tree, which the **agents path** needs (the retrained repository holds its
  runtime and its routing on different branches, and its routing accepts runtime v0.1.0 only). Without
  `--specialist`, the website path runs this copy too, as before.

Each driver replies to its runtime in the shape that copy's own contract takes (`runtime-reply.mjs`): v0.1.0 the
completed or failed objects the drivers always returned; v0.2.0 the website's generation result, built by the copy's own
synthetic callbacks module (`generationResult`, `failureResult`); any other contract stops the driver ("not runnable",
exit 3), so its gates are NOT RUN with that reason. Nothing of the agents repositories is copied into the kit. Every
run names the copy each path was given by its `.kit-archive-commit` and its `RUNTIME_CONTRACT_VERSION`: `results.json`
(`specialist_copy`, `specialist_commit`, `specialist_contract`, `agents_copy`, `agents_commit`, `agents_contract`,
recorded before the service starts) and the "Copies" lines of `summary.md` (each with its path's not-run reason when
that path did not run: `not_run.website_path`, `not_run.agents_path`); each driver's records (`runtime_contract`); and
the wiring record (`specialist_commit`, `specialist_contract` and `agents_commit` in `TESTED.json`). The readiness
check's row "simulation runtime copy" (playbook step 14) is PASS only when the website path ran the runtime pin
(`agents_pins.runtime`: its commit and contract; the path ran when `results.json` has no `not_run.website_path` and holds
the website driver's own line, `subchecks.website_driver`). A run whose website path did not run (the service refused
to start, as on a pre-build commit, or the driver stopped), a run without `--specialist`, or one with another commit
leaves it NOT RUN: the pinned runtime was not simulated.

## Parts

| File | Role |
|---|---|
| `run_sim.py` | orchestrates the steps below, then the gates; every missing part makes its gates NOT RUN with the reason that part gave |
| `gates.py` | the eight gates as pure functions of the records; the NOT RUN rule |
| `compare.py` | the G-EQ projection of a receipt and of an arena record, field by field (`VOLATILE.md`) |
| `reference.py` | `run_arena.run_round` on a copy of the corpus; the kit-derived decision on each genuine receipt (G-DEL); `run_contained.py` when the overseer is on the tree |
| `fixture_verifier.py` | the arena's fixture-serving rule as the service applies it; parity-tested against `run_arena` |
| `faults.py` | the arena's own mutations and the STEM mutations, applied by the arena's own functions, and the fault round only the service loads |
| `tamper_web.py` | the tampering cases W-T1 to W-T8 through the Worker's release-gate module alone (a sub-check) |
| `website-driver.mjs` | replays the website users of `users.json`, the tampering cases and the website-path fault cases through the disposable export |
| `agents-driver.mjs` | the harness's router, the kit's router port, the harness's offline runtime and the specialist port, without the website |
| `runtime-reply.mjs` | the reply both drivers give their runtime copy, in the shape that copy's contract takes (above) |
| `users.json` | 26 simulated users, sessions of one to four turns, each turn naming a corpus item and an action |
| `corpus/synthetic/s1/` | the synthetic corpus in the arena round format (`integration/tools/build_corpus.py`) |
| `corpus/DATA-TERMS.md`, `corpus/MANIFEST.sha256` | the corpus's terms and digests |
| `TESTED.json` | the record of the last wiring run with the test double (below); it names the files it ran |

## The steps

1. **Copies.** The corpus (and any `--rounds` Daniel supplies, D15) is copied twice: one copy for the service, one for the
   reference harness. The kit and the rounds are never written to.
2. **Fault cases.** `faults.fault_cases` applies the arena's own mutations (and the STEM mutations on STEM items) to the
   reference copy's answers; `faults.write_fault_round` indexes each mutated answer to its item's own fixtures in a round
   of its own of the **service** copy only (`sim-fault-<item>~<kind>/`, the item under its own name), so the service
   serves it as the arena's mutation pass does (by claim id, bound to the claim text: a re-stated claim is refused as
   stale).
3. **The service** (`integration-sim` profile, ephemeral keys, the fixture provider over the service copy, the evidence
   tap, loopback). Its per-token rate is raised for the simulation only (`EPINOIC_RATE_PER_MINUTE=6000`: one token
   replays every user back to back, two requests per turn). Its output goes to `<out>/work/service.log`.
4. **The website driver** (`website-driver.mjs`): one fresh world per simulated user (the export's `tests/helpers/d1.js`
   D1 with its migrations, `APP_ENV=development`, `CHAT_BACKEND=verified`, `KIT_SIMULATION=1`, the mock subject router,
   a loopback principal), `POST /api/chat` through the export's `handleRequest` with `options.verified.inner` = the
   export's `createSpecialistOrchestrator` over the runtime copy's `createOfflineTestRuntime` (`--specialist`, else
   `--agents`; the synthetic History bundle and gate configuration unchanged; the simulation's synthetic English
   specialist is the same entry under its slug with the sources line optional). The runtime's `authorizedGenerate`
   returns the turn's corpus answer (or a fault case's mutated answer) in the copy's own contract; no model is
   called. The actions: send, follow-up, retry, cancel (during the specialist's generation), two concurrent sends into
   one conversation, the service stopped (then a retry with it back), a service slower than the budget (a fake clock
   leaves just over `checks_min_ms`; the service never answers),
   a fake clock past the handshake cache age, a handshake mismatch, a subject unavailable after routing, a mixed
   subject, and the tampering cases W-T1 to W-T8 (the service's real verdict for the turn, changed on its way back as the
   case's vector changes the bound deliver vector). It records each response, the D1 row, the calls made, the verdicts,
   what the page would display (`checksBadge`, `checkLabel`, the scope statement) and the invariants of G-INV.
5. **The agents driver** (`agents-driver.mjs`): the harness copy's `selectSpecialist` over its synthetic catalogue (the
   availability of the runtime it routes to), the kit's `router-port.js` (one slug, a clarification or unavailable,
   rows of the `sim` environment and the service rows), the offline runtime (History, English and Physics synthetic
   specialists), the kit's A2 envelope (`integration/agents/checks-port/`) and `POST /v1/turns/check`: STEM, duplicate
   (clean and conflicting), combined (refused `KIT-REQ-002` while the combinator is not connected) and clarify (no
   specialist or checks call), then the STEM fault cases.
6. **The reference** (`reference.py`) on the other copy, then the tampering sub-check at the adapter, then **the gates**
   from the drivers' records and the evidence tap (`run_sim.collect`).

## What runs on this tree, and what is connected with the rebuilt overseer

The overseer package is not on this tree, so the checks service refuses to start (`KIT-HS-007 overseer_unavailable`).
`run_sim.py` reports that refusal as the reason of every website-path and agents-path gate, every gate is NOT RUN,
never PASS, and the exit status is 1. What still runs: the fault cases (sub-check `fault_cases`), the reference harness
on a copy (sub-check `arena:s1`: every genuine and mutation record functional, the round not qualified), and the
tampering cases through the release-gate module alone (sub-check `tamper_adapter`; evidence about one module, never
the gate).

Connected when the rebuilt overseer is merged (the pre-build notes list them): its port adapter (the service then
starts and the drivers run), the contained run for G-EQ-CONTAINED, and the probe providers through the asynchronous
review for G-OVS.

## The wiring check with a test double (tests only)

```
python integration/sim/run_sim.py --website <patched export> --specialist <runtime copy> --agents <harness copy> \
    --translator <kit> --corpus <kit>/integration/sim/corpus --out <dir> \
    --test-overseer-port kit_overseer_test_double --test-pythonpath <kit>/tests/integration/sim_double:<kit> \
    [--record-wiring <kit>/integration/sim/TESTED.json]
```

`tests/integration/sim_double/kit_overseer_test_double.py` is a test double of the overseer port
(`tests/integration/helpers.RecordingPort`, kept per call): fixture clearances, a FINAL audit that passes, a delivery
of the call's first reply. It audits nothing, so under it **every gate is NOT RUN** ("the overseer port is a test
double") and the exit status is 1; what each gate computed is kept only as the sub-checks `gates_with_test_double` and
`gate_cases_with_test_double`. `--record-wiring` writes `TESTED.json`: the digests of the files the run used, the
export's provenance, the commits of both copies with the runtime copy's contract, and what each gate computed.
`tests/integration/test_sim_wiring.py` fails when one of those files changes after the record was written.

The last wiring run (`TESTED.json`; information only, under the double) computed PASS for G-EQ-ARENA, G-INV, G-HON,
G-DEL and G-TAMPER, NOT RUN for G-EQ-CONTAINED and G-OVS, and FAIL for G-FAULT on the cases it names: mutations the arena names only by a warning-level finding (an unverifiable
invented quotation, `CORE-SRC-003`; a self-certification, `CORE-SELF-001`) are delivered by the kit's decision table,
which refuses on error findings and negative results only (D3). Whether such an answer is withheld is the rebuilt
overseer's delivery rule or a new decision: recorded in the pre-build notes for the overseer step, never changed here.

## Which gates have material on the synthetic corpus

Established at kit build (the NOT RUN rule): G-EQ-ARENA, G-FAULT, G-INV, G-HON, G-DEL and G-TAMPER have material on
the synthetic corpus once the website path exists. G-EQ-CONTAINED and G-OVS need the overseer's contained run. Without
`corpus/licensed/` (decision D15), these are NOT RUN on the synthetic corpus: the re-keyed pass, the adjudicated genuine
faults, the recorded overseer reports and any real cheapest-tier translation.

## Request ids and digests

A website-path call's request id is the website's attempt id; the arena's is `req-<item>` (`req-<group>` for a
grouped item). The fixture provider serves each fixture recorded under the arena's request id of its item under the
request id of the claim it translates (`RekeyingFixtureProvider`; a no-op in the arena), so the encoded problems differ
only by that id; a fixture recorded for another request (an adversarial variant reusing another item's fixture) is
served as it is and refused as the arena refuses it. That is also why each fault case is its own round of the service
copy (`sim-fault-<item>~<kind>/specialists/<item>.json`): the item keeps its name, so its arena request id. G-EQ compares the problem and binding digests with the problem's request id
normalised (`compare.result_digests`): every other byte of the problem, the configuration, the versions and the limits
still count (`tests/integration/test_fixture_parity.py` shows the normalised digests equal on both paths).
