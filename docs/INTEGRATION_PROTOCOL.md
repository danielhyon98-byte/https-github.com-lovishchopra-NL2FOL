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

The kit (`integration/`) adds the Worker's adapter and its tests, the website patch material for base M, the agents
checks-port package, the golden vectors shared by the three repositories, the simulation and its gates, the readiness
scripts, the rollback plan and the playbook a fresh session follows ([`integration/PLAYBOOK.md`](../integration/PLAYBOOK.md)).
The decisions still open, with the fail-closed default the kit implements for each, are in
[`integration/DECISIONS.md`](../integration/DECISIONS.md).

## State on the pre-build branch

The overseer package and the argument diagnostics are built by other work streams and connected in phase 2. The
named-policy allowlist of contract 0.3 and the closed transformation values came with the end-to-end fixes, merged
into this branch on 17 October 2026 (the contract line now says 0.4). The flash-router sub-project (`flash-router/`)
and the combinator sub-project (`combinator/`) are in this kit, each edited and released apart from the Z3
infrastructure; the combinator is connected to the service in phase 2. On this branch the service therefore refuses
to start with `KIT-HS-007 overseer_unavailable` (no overseer port adapter); before that merge it stopped earlier, at
`KIT-HS-006 named_policies_unavailable`. Every part that does not depend on the overseer is built and tested, against
fixtures where a port's other side is missing (`RecordingPort` is a test double of the overseer port in
`tests/integration/helpers.py`, never importable by the package). Nothing is deployed and no live provider has been
called.
