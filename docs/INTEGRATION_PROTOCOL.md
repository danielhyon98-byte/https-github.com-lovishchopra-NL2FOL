# Integration protocol `epinoic.integration.v1` (translator documentation)

The integration kit (`integration/`) connects the translator's Z3 engine, its STEM front end, its branch parsers and
its overseer with the website (a Cloudflare Worker) and the agents repository's specialist runtime. The normative
text is [`integration/PROTOCOL.md`](../integration/PROTOCOL.md); this page says what the translator provides and where.

**Z3 and STEM checks are required.** No mode shows a specialist answer as checked without them. A missing required
part fails loudly with a named code before the service binds a socket: Z3 itself (`KIT-HS-003 z3_unavailable`, from a
standard-library bootstrap, exit status 2, no traceback), the STEM branches (`KIT-HS-005`), the named policies
(`KIT-HS-006`), the overseer (`KIT-HS-007`), the keys (`KIT-HS-008`) and the rest of `KIT-HS-001` to `KIT-HS-016`.
Results prove properties of the logic encoding only, and every verdict carries the engine scope statement verbatim.

## What the translator provides

| Part | Where |
|---|---|
| the protocol's models, canonical JSON, closed codes, generated compatibility pins | `src/epinoic_logic/integration/` (`protocol.py`, `canonical.py`, `errors.py`, `compat.py`) |
| the service profiles `integration` and `integration-sim` | `python -m epinoic_logic.integration serve` (or `epinoic-logic serve` with `EPINOIC_PROFILE`); the default profile `engine` is unchanged and adds no route |
| bootstrap, preflight, self-test, capabilities | `bootstrap.py`, `preflight.py`, `selftest.py`, `capabilities.py` (`GET /v1/capabilities`) |
| the required checks port | `checks_port.py`, `turn.py` (`POST /v1/turns/check`, behind the service's existing gates) |
| the specialist port (runtime results v1 and v2) | `specialist_port.py` |
| the overseer port (the overseer as a separate sub-project) | `overseer_port.py`; the embedded adapter `epinoic_overseer.port` is connected in phase 2 |
| the combinator port (the combinator as a separate agent) | `combinator_port.py` (input, output, refusal, hello, the published contract and its digest, the `synthesis/1.0` payload the hub receives); the combinator itself is the sub-project `combinator/` (package `epinoic_combinator`), never imported by the translator; `combined` is not offered until it is connected (phase 2) |
| the flash-router port (the oversight planner as a separate, independent sub-agent) | `router_port.py` (the router run in its own process: `router_child.py`), `routing_features.py`; the router itself is the sub-project `flash-router/` (package `epinoic_flash_router`), attached only when `EPINOIC_FLASH_ROUTER` names it; without it the minimum-oversight floor runs |
| the decision table, verdict signing, the Worker's binding checks | `delivery.py` |
| the fixture provider of the simulation (the arena's serving rule) | `verifier.py` (`FixtureCorpus`) |
| the STEM budget as a per-channel parameter | `channel/bus.py` (`stem_budget_s`, bounded by `STEM_CHECK_BUDGET_S`) |

The kit (`integration/`) adds the Worker's adapter and its tests, the website patch material for base M and the W0
docs drafter, the agents material (the checks-port package A2, and the changes A3 and A5 as anchored replacements with
their applier), the golden vectors shared by the three repositories, the simulation (its website and agents drivers and
its gates), the readiness scripts, the rollback plan and the playbook a fresh session follows
([`integration/PLAYBOOK.md`](../integration/PLAYBOOK.md)). Every decision of the kit is decided, under Daniel's
delegation of 17 October 2026; the record, and the kit changes those decisions require (not made yet: the defaults stay
fail-closed until they are), are in [`integration/DECISIONS.md`](../integration/DECISIONS.md).

## Rules the checks port keeps (pre-build verification, third round)

- **Never raises.** Whatever an overseer-port adapter raises, `SystemExit` included (only `KeyboardInterrupt` goes
  through), the call answers a signed `refuse_incomplete` `KIT-DL-900` verdict, never an HTTP 500; a failure of the
  asynchronous review changes neither the decision nor its reasons.
- **Counts over every claim.** `counts.budget_skipped` names `KIT-DL-013` over all claims, and the Worker re-derives the
  same reasons from it, whatever the capped list of 32 holds.
- **The review of a refused call.** A call refused before delivery still has its review planned and queued over the
  outputs received; one refused before any output has nothing to review, and its evidence says so.
- **Names.** The hub names each specialist `<slug>-specialist`, as the arena does, so its credit rules read it; verdicts
  keep the protocol ids. No router may be named by the floor's reserved identity (`minimum-oversight-floor`).
- **Profiles and adapters.** A misspelled `EPINOIC_PROFILE` is refused (`KIT-HS-012`); `POST /v1/outcomes` takes an
  adapter only from a closed allowlist; the checker's configuration shows no key in its `repr`.
- **The Worker's release gate** binds the released text to the deliverable's `answer_sha256` whatever produced the
  result, and reads the specialist runtime's own capabilities (`entries`).

## State on the pre-build branch

The overseer package and the argument diagnostics are built by other work streams and connected in phase 2. The
named-policy allowlist of contract 0.3 and the closed transformation values came with the end-to-end fixes, merged
into this branch on 17 October 2026 (the contract line now says 0.4). The flash-router sub-project (`flash-router/`)
and the combinator sub-project (`combinator/`) are in this kit, each edited and released apart from the Z3
infrastructure; the combinator is connected to the service in phase 2. On this branch the service therefore refuses
to start with `KIT-HS-007 overseer_unavailable` (no overseer port adapter); before that merge it stopped earlier, at
`KIT-HS-006 named_policies_unavailable`. Every part that does not depend on the overseer is built and tested, against
fixtures where a port's other side is missing (`RecordingPort` is a test double of the overseer port in
`tests/integration/helpers.py`, never importable by the package). The simulation's drivers run end to end against
the service only with a test double of the overseer port (`tests/integration/sim_double/`), a wiring check under
which every gate is NOT RUN (`integration/sim/README.md`). The argument diagnostics are not on this branch either: when
they merge, the engine, policy and translator versions they bump must be added to `COMPATIBILITY.json`, the
routing request's diagnostics connected (`routing_features.OutputRecord.diagnostics`) and `minimum-oversight-floor/2`
adopted (D29). Nothing is deployed and no live provider has been called.
