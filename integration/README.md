# Integration kit: required Z3 and STEM checks on top of the specialist APIs

The kit integrates the translator's Z3 engine (with its STEM front end, its branch parsers and its overseer) with the
website (a Cloudflare Worker) and the specialist runtime of the agents repository, through the protocol
`epinoic.integration.v1` ([PROTOCOL.md](PROTOCOL.md)). **Z3 is not optional**: no mode releases a specialist answer
as checked without the required Z3 and STEM checks, and a missing required part fails loudly with a named code.
Results prove properties of the logic encoding only.

**Start here:** a fresh session follows [PLAYBOOK.md](PLAYBOOK.md) from step 0. The playbook is reference material: it
authorizes nothing in any repository. The open decisions and the defaults the kit implements until each is decided are
in [DECISIONS.md](DECISIONS.md).

## Status

| Part | State on this branch |
|---|---|
| protocol, five ports, codes, compatibility (`src/epinoic_logic/integration/`) | built and tested |
| service profiles `integration` / `integration-sim`, bootstrap, preflight, self-test, capabilities, `POST /v1/turns/check` | built and tested; the service **refuses to start on this branch** with `KIT-HS-007` (no overseer port adapter) until phase 2 connects it. Contract 0.3's named policies were merged into this branch with the end-to-end fixes on 17 October 2026; a pre-build commit before that merge stops earlier, at `KIT-HS-006` |
| TurnChecker (normative order, budget, STEM budget, prefetch, decision table, signing, review routing) | built; tested through `RecordingPort`, a test double of the overseer port |
| flash-router port: request, plan, hello, floor, admission; the router run in its own process | built and tested |
| flash router (`flash-router/`, package `epinoic_flash_router` 0.1.0) | a separate, independent sub-project with its own `pyproject.toml`, rules, cost model and conformance suite; built and tested; attached only when `EPINOIC_FLASH_ROUTER` names it (decision D28) |
| overseer port adapter (`epinoic_overseer.port`) | **connected in phase 2** (the overseer is not on this branch) |
| combinator | **connected in phase 2**; until then `combined` is not offered |
| website adapter (`website/src/verify/`) and its `node:test` tests | built and tested in the kit; the website patch set is described in `website/PATCH-PLAN.md` |
| agents patch plan (`agents/PATCH-PLAN.md`) | written; the agents-side code is written in that repository (D20) |
| simulation (`sim/`) | gates, comparison, reference harness, fixture verifier, corpus and users built and tested; the website-path and agents drivers are connected in phase 2, so every gate is NOT RUN here |
| readiness (`readiness/`), rollback (`rollback/`), container (`deploy/container/`, PROPOSED) | written |

Nothing is deployed, no provider is called, and no live integration is claimed anywhere in the kit.

## Layout

```
integration/
  README.md  PLAYBOOK.md  PROTOCOL.md  DECISIONS.md
  COMPATIBILITY.json            the pinned compatibility set (PROTOCOL.md section 13)
  subject-map.json              website route <-> agents slug <-> translator subject <-> branch, per environment
  MANIFEST.sha256               SHA-256 of every kit file (integration/ and src/epinoic_logic/integration/)
  schemas/                      JSON Schemas generated from the pydantic models (drift-tested)
  vectors/                      golden vectors shared by all three repositories (synthetic data only)
    canonical/ handshake/ decision-table/ verdict-binding/ chat-contract/ codes/ router-port/
    specialist-port/v1/ specialist-port/v2/
  tools/                        generate.py (compat, schemas), vectors.py, build_corpus.py, manifest.py
  website/
    src/verify/                 the Worker's adapter: canonical-json, sha256, compat, subject-map, codes, decision-table,
                                release-gate, specialist-port, router-port, translator-client, verification,
                                with-verification, specialist-orchestrator (simulation only)
    tests/                      node:test files (kit-vectors.js finds the vectors in the kit or in tests/fixtures/kit/)
    PATCH-PLAN.md  ANCHORS.md   the website change plan (W0 to W8) and its anchors
  agents/PATCH-PLAN.md          the agents change plan (A0 to A5)
  sim/                          the local end-to-end simulation (sim/README.md)
  readiness/                    locate.sh, check.py, check-website.mjs, check-agents.mjs
  overseer-port/CONFORMANCE.md  what an overseer adapter (embedded or sidecar) must reproduce
  router-port/CONFORMANCE.md    what the flash-router sub-project must reproduce
  deploy/container/             PROPOSED container files; built and deployed only on the owners' go-ahead
  rollback/ROLLBACK.md          rollback per repository; prints commands, runs nothing
src/epinoic_logic/integration/  the service side (installed with the package)
flash-router/                   the flash router: its own sub-project (pyproject.toml, src/epinoic_flash_router/, tests/),
                                standard library only at run time, never imported by the translator
tests/integration/              the kit's Python tests; tests/fixtures/integration/ the runtime fixtures (SOURCE.md)
docs/INTEGRATION_PROTOCOL.md    the protocol in the translator's documentation set
```

## Regenerating generated files (never edit them by hand)

```
python integration/tools/generate.py        # compat.py, compat.js, subject-map.js, schemas/  (--check to verify)
python integration/tools/vectors.py         # vectors/                                        (--check)
python integration/tools/build_corpus.py    # sim/corpus/synthetic/                           (--check)
python integration/tools/manifest.py        # MANIFEST.sha256 files, last                     (--check)
```

## The translator side, step by step (T1 to T10)

- **T1. One committed base** with the overseer, contract 0.3 and the named policies, and any later fix branch Daniel
  names; the full suite, the overseer suite and the contained run pass on it. This pre-build branch is **not** that
  base: phase 2 merges it into the integrated tree.
- **T2.** Models, canonical JSON, codes, compatibility generation, bootstrap and `__main__` (standard library only),
  lazy engine imports in `cli.py`.
- **T3.** Profiles, settings (failing closed, secrets out of `repr`), preflight, self-test, capabilities.
- **T4.** TurnChecker, the budget, the prefetch and the STEM budget as a per-channel parameter bounded by
  `STEM_CHECK_BUDGET_S` (`channel/bus.py`), the decision table, the delivery rule and verdict signing.
- **T5.** `POST /v1/turns/check`; the existing routes and their behaviour do not change; the default profile stays
  `engine`.
- **T6.** The overseer port's embedded adapter, its conformance suite and the asynchronous review queue
  (**phase 2**); the flash-router sub-project behind the router port (built: `flash-router/`, run in its own process).
- **T7.** The website adapter and its tests; patch sets M (against `2cd3182`) and P (when a base-P website exists);
  `apply.mjs`, `ANCHORS.md`, `RESULT.sha256`; the vectors.
- **T8.** The simulation: the synthetic corpus in the arena round format, the reference harness, the comparison, the
  faults, the fixture verifier, the tampering cases, the drivers, the readiness scripts.
- **T9.** Docs: `integration/*.md`, the integration contract 0.4, the README pointer. Engine and policy semantics do
  not change. The manifest is generated last.
- **T10. Publishing** is Daniel's action after D20: an annotated tag `integration-kit-v1` on the kit commit, pushed to
  the canonical remote only, and `INTEGRATION_KIT.md` on that remote's default branch naming the tag. A tag is never
  moved; a corrected kit gets a new tag.
