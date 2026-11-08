# Epinoic AI flash router (`epinoic-flash-router`)

The flash router is the **oversight planner's decision maker**: it decides **how the overseer reviews**. Per request
and per specialist output, for the translator's checks service: one instance reading the output whole (`IN_DEPTH`),
the work divided across parallel instances (`SPLIT`), independent duplicate reviews (`DUPLICATE`), or, for a combined
answer, each source reviewed on its own and the combinator's output reviewed against all of them (`N_FOLD`). Per batch,
for the overseer pool: which overseer instances review which dossiers, and which dossiers go to independent duplicates.

It is **not the translator's `RouterHub`** (which carries the messages between agents through the translator channel),
and not the website's subject routing (which picks a specialist). It plans reviews; it never carries, checks, delivers
or decides anything about an answer.

It is a **separate, independent agent** in a sub-project of its own: its own `pyproject.toml` and version (0.2.0),
this README, `docs/DESIGN.md`, its rules and cost data as **versioned data files with digests**, a runner, and its own
tests. It needs nothing but the Python standard library at run time and never imports the translator, the engine, Z3,
the STEM support or the overseer, so it is edited, re-tuned and released without touching any of them. It talks to them
only through the router port `epinoic.integration.router-port.v1` (the translator's `integration/PROTOCOL.md`, sections
7a and 7b).

## The router port

| Function (`epinoic_flash_router.port`) | Caller | In | Out |
|---|---|---|---|
| `hello()` | the checks service | nothing | `router-hello.v1`: identity, methods, profiles, `tier: "cheapest"`, `deterministic: true` |
| `plan(request_json)` | the checks service | `routing-request.v1` (features only) | `routing-plan.v1` |
| `pool_hello()` | the overseer pool | nothing | `pool-router-hello.v1`: identity, the capability `pool-plan`, pool port version 1.1 |
| `pool_plan(request_json)` | the overseer pool | `pool-routing-request.v1` (positions and risk classes only) | `pool-routing-plan.v1` |

Same input, same plan: every function is pure and deterministic (no network, no clock, no randomness, no model call; the
data were read once, at load). `FlashRouter(data_dir)` is the same API over another data directory.

**The runner** operates the router as a separate sub-agent from the command line, over the same port:

```
python -m epinoic_flash_router_cli hello                     # or: epinoic-flash-router hello
python -m epinoic_flash_router_cli plan < routing-request.json
python -m epinoic_flash_router_cli pool-hello
python -m epinoic_flash_router_cli pool-plan < pool-routing-request.json
python -m epinoic_flash_router_cli identity
python -m epinoic_flash_router_cli pool-plan --data DIR < pool-routing-request.json   # a re-tuned copy of the data
```

The answer is written to standard output as canonical JSON with no trailing newline; exit status 2 when the data cannot
be loaded, 3 when the input is not a request this router reads (the reason on standard error, never a plan).

## How it is attached, and why its plan is only advice

- **By the checks service**, only when named: `EPINOIC_FLASH_ROUTER=epinoic_flash_router.port`. Unset or `none` (the
  default): detached, and the service runs its minimum-oversight floor (`minimum-oversight-floor/1`) for every review.
- **By the overseer pool, by capability**: `OverseerPool(pack, providers, router="epinoic_flash_router.port")` (or the
  delivery policy's `router=`). The pool attaches the router only when its module exposes `pool_hello()` and
  `pool_plan()` and its pool hello declares the `pool-plan` capability at a pool port version the overseer speaks;
  otherwise it is refused (`KIT-RT-015`) and the overseer's floor plan runs. Without a router, the floor plan runs.
- **In its own process**: both callers run each call with `python -I`, their own import path and an environment that
  holds no `EPINOIC_` variable (no key, secret or token), within a time limit. Whatever this code raises, prints or
  patches stays in that process. A fault boundary, not a sandbox: that process runs as the caller's user, so install
  this router only as code trusted with that user (the translator's `integration/PROTOCOL.md` section 7a, decision D28).
- **Advisory, under the minimum-oversight floor**: everything it answers is validated as untrusted data; a plan out of
  contract is refused with its `KIT-RT` code, a plan below the floor with `KIT-RT-020`, a failing router with
  `KIT-RT-016`, and the floor plan runs. The floors are the callers' own code (the service's in the translator's router
  port; the pool's, `minimum-oversight-floor/pool-1`, in the overseer), computed from the same risk signals: every
  dossier reviewed, two independent instances for a dossier with a repeated fault or a risk signal. So accuracy never
  depends on how this router is edited: it can add oversight (more duplicates, smaller batches), never remove it, and it
  never changes a clearance, a delivery or a decision. Every plan records this router's identity (name, version, the
  digests of its rules and of its cost data).

## The data files (`src/epinoic_flash_router/data/`)

| File | What it holds |
|---|---|
| `data/MANIFEST.json` | the current rules and cost-data files, and every data file's version, release and digest |
| `rules-2.json` (current, 0.2.0) | rules/2 in words; the port planner's parameters (`split_words` 900, `max_parts` 16, `max_reviews` 4, `hard_max_instances` 64, `context_max_bytes` 65,536); the pool planner's thresholds and batch size (`escalated_reviewers` 2, `baseline_reviewers` 1, `record_weight` 2, `batch_size` null: the pool's own quota); the agreement signals the port rules read; the features each planner reads; the method table |
| `cost-data-2.json` (current, 0.2.0) | the port plan's planning estimates (not measurements) and the sizes the overseer recorded for its knowledge pack and dossiers; no price, no latency, no model |
| `rules-1.json`, `cost-data-1.json` | 0.1.0's rules and cost model, kept byte for byte their 0.1.0 digests |

A digest is the SHA-256 of the document's canonical JSON (keys sorted, no whitespace, non-ASCII raw); the identity
reports the current files' digests. With the released rules the pool plan is the plan the overseer's own planner made
before the decision moved here, for every recorded transfer (the overseer's `test_flash_router_pool.py`). The cost
planner and the fast profile are deferred: the pool plan estimates no cost, and the recorded sizes wait for it.

## Re-tuning and releasing a change

1. Copy the current rules (or cost-data) file to the next version's name (`rules-3.json`), edit it, and try it without
   releasing it: `python -m epinoic_flash_router_cli pool-plan --data <a copy of data/>`, or
   `FlashRouter("<a copy of data/>")`. The plan names the copy's digest.
2. Make it current in `data/MANIFEST.json` with its digest, its version and the release; bump `version` in
   `pyproject.toml` and `__version__` in `src/epinoic_flash_router/__init__.py`; pin the new file's digest in
   `tests/flash_router_tests/test_data.py` (a released file never changes in place).
3. Run this suite. Nothing in the translator, the engine, the STEM support or the overseer changes, unless the router
   port itself changes (a new port version, agreed with its owner).

A weakened file (fewer reviewers for an escalated dossier) loads and plans, and the overseer refuses its plans below
the floor (`KIT-RT-020`); the overseer's tests show it on a scratch copy.

## Tests

```
python -m pytest -q          # from this directory: tests/flash_router_tests
```

From the translator's repository root, its documented command (`python -m pytest -q`) runs this suite too, beside the
translator's and the overseer's, and `tests/integration/test_flash_router_subproject.py` runs it once more from this
directory. The suite shows the router port's conformance items over the router-port vectors (`tests/vectors/router-port/`,
copied here by the translator's `integration/tools/vectors.py`; change the kit's generator, never this copy) and over
generated requests, validated with the translator's own `epinoic_logic.integration.router_port` and `router_pool`
(pydantic and the standard library: no engine, no Z3, no overseer); the pool plans; the data files, their manifest and
pinned digests; the runner; determinism in a fresh interpreter; and that the router runs with nothing but its own `src/`
on the path. Inside the translator repository `tests/flash_router_tests/conftest.py` uses its `src/`; a split copy uses
the translator package installed in its environment.

## Repository form (decisions D20 and D28) and splitting it into a repository of its own

This router is a sub-project directory of the translator's development branch, not a repository or a submodule of its
own: no new repository is created (D20). A verified version is published as the branch `subproject/flash-router` of
the translator's `origin`, by `git subtree split --prefix flash-router` (fast-forward only), and it is released by its
own version and identity, never by the kit tag. Two couplings remain while it lives in the tree, both decided: the
translator's suite runs this suite (D28), and `tests/vectors/router-port/` is the kit's copy (above).

The sub-project is split-ready: every path it uses is inside `flash-router/`, but for the translator's router port its
tests validate against. No repository is created or pushed by this tree. To split it:

```
git subtree split --prefix flash-router -b flash-router-split   # a branch whose root is this directory, with its history
git init <new repository> && git -C <new repository> pull <translator checkout> flash-router-split
pip install -e "<translator checkout>"                          # the router port its tests validate against
pip install -e "<new repository>[dev]"
python -m pytest -q                                             # from <new repository>
```

Then the translator keeps `EPINOIC_FLASH_ROUTER` and the overseer its `router=` argument, both naming
`epinoic_flash_router.port` from the installed package instead of the sub-directory; the translator's
`integration/tools/vectors.py` stops writing `tests/vectors/router-port/` and the split copy keeps its copy.
