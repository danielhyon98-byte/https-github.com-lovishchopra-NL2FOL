# Epinoic AI flash router (`epinoic-flash-router`)

The flash router is the **oversight planner's decision maker**: it decides **how the overseer reviews**. Per request
and per specialist output, for the translator's checks service: one instance reading the output whole (`IN_DEPTH`),
the work divided across parallel instances (`SPLIT`), independent duplicate reviews (`DUPLICATE`), or, for a combined
answer, each source reviewed on its own and the combinator's output reviewed against all of them (`N_FOLD`). Per batch,
for the overseer pool: which overseer instances review which dossiers, and which dossiers go to independent duplicates.

Its first decision, for every response it is asked about, is the **flash decision maker** (`decision.py`, rules D1 to D7
since 0.3.0, of `rules-4.json` since 0.4.0): reading the user's request record and each specialist output as features only, it
decides between the **in-depth examination method** (one cheapest-tier overseer instance examines the whole response,
`IN_DEPTH`) and the **duplication method** (the work split across several cheapest-tier instances in parallel: `SPLIT`
parts of one output, `N_FOLD` for a combined answer; with independent duplicate reviews, `DUPLICATE`, where risk calls for
agreement), choosing **the cheapest that keeps accuracy** from the recorded cost data (`cost-data-4.json`): agreement (the
reviews risk calls for; risk signals only raise them), fit (one instance must read the pack's system text its content
needs, what it examines and the output budget within the instance budget) and cost (tokens, then agent-seconds, then
calls). The decision is code, deterministic and instant: no model decides duplication, and the overseer's optional
escalation advisor can only add escalations. Every decision is recorded with the features it read, every candidate it
priced (whether it keeps accuracy, and why it was or was not chosen) and its reasons, closed codes and integers only.
What cannot be divided and does not fit one instance is disclosed (`over_budget`), never shortened: a pool dossier, and
a combined answer's merged review, which reads the synthesis and every source whole (since 0.4.0 at the service's port
too, as in the pool). The system text priced is the one the overseer sends: `cost-data-4.json` records the sizes of the
overseer's pack 2.1 (0.3.0's cost data recorded pack 2.0's, 13,360 characters smaller in every composition, so a dossier
whose need lay within about 3,340 tokens under the budget was recorded as fitting when it did not).

It is **not the translator's `RouterHub`** (which carries the messages between agents through the translator channel),
and not the website's subject routing (which picks a specialist). It plans reviews; it never carries, checks, delivers
or decides anything about an answer.

It is a **separate, independent agent** in a sub-project of its own: its own `pyproject.toml` and version (0.4.0),
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
| `pool_hello()` | the overseer pool | nothing | `pool-router-hello.v1`: identity, the capability `pool-plan`, pool port version 1.2 (methods `IN_DEPTH`, `DUPLICATE`, `N_FOLD`) |
| `pool_plan(request_json)` | the overseer pool | `pool-routing-request.v1` at pool port 1.1 or 1.2 (positions, risk classes, at 1.2 sizes and a combined answer's parts) | `pool-routing-plan.v1` at the request's version (at 1.2 every dossier's decision record, and a combined answer N_FOLD) |

Same input, same plan: every function is pure and deterministic (no network, no clock, no randomness, no model call; the
data were read once, at load). `FlashRouter(data_dir)` is the same API over another data directory.

The service's plan carries each transfer's method, reviews, parts, reasons, features used and estimated cost in the
router port's closed vocabulary, and the plan is built from the flash decision maker's record of every transfer
(`epinoic_flash_router.planner.transfer_decisions(request)`: the candidates priced, the fit, the reasons; for a combined
answer's synthesis the N_FOLD record with each source's decision and the merged review's). Router port 1.0's reason
codes have none for `over_budget` or `split_to_fit`, so a transfer one instance cannot read whole is disclosed in that
record, not in the service's plan, until the port adds the code (a router port change, agreed with its owner). A
routing request that names one transfer key twice is refused, as the router port refuses it (every transfer is one
entry, port rule 1).

**What it reads of a request** (`epinoic_flash_router.contract`). Before anything is planned, every request is checked
against what the planners read of it: JSON text (no `NaN` or `Infinity`, no member named twice in one object, no string
it cannot write as UTF-8) whose every member the planners read has the type and the range the router port gives it,
every count at most 2^53 - 1 (the protocol's integers). A request it does not read is refused with `RequestError` (a
`ValueError`) naming the member and the rule, never a value of the request: `limits.per_instance_quota is an integer
from 1 to 9007199254740991`, say. So a request that passes cannot make the planners fail, and what they raise on one is a
fault of the router's own code, never of the request: the runner reports the two apart (exit 3 and exit 4, below). The
checks are no stricter than the router port (each rule is implied by the port's own validation of that member, and the
members the planners do not read are left to the callers, which validate the whole request before they send it), so
every request in contract is planned exactly as before: the plans of 8,011 port-validated requests (the router-port
vectors, 4,000 of the service's and 4,000 of the pool's at 1.1 and 1.2) are byte for byte those of the router before the
checks, which is why the identity did not change.

**The runner** operates the router as a separate sub-agent from the command line, over the same port:

```
python -m epinoic_flash_router_cli hello                     # or: epinoic-flash-router hello
python -m epinoic_flash_router_cli plan < routing-request.json
python -m epinoic_flash_router_cli pool-hello
python -m epinoic_flash_router_cli pool-plan < pool-routing-request.json
python -m epinoic_flash_router_cli identity
python -m epinoic_flash_router_cli pool-plan --data DIR < pool-routing-request.json   # a re-tuned copy of the data
```

The answer is written to standard output as canonical JSON with no trailing newline. Otherwise nothing is written to
standard output, one line on standard error names the reason, and there is never a traceback:

| Exit | When | Standard error names |
|---|---|---|
| 0 | the answer was written | nothing |
| 2 | the data cannot be loaded: a file that cannot be read, that is not JSON or not the shape the planners read, or that is nested too deep to decode | the exception type and the loader's reason (`OSError`, `ValueError`; `RecursionError` by its type) |
| 3 | the input is not a request this router reads: standard input that is not text, or a request the router refuses (a request nested too deep to decode, a number out of range, a zero quota, a transfer key named twice, ...) | `RequestError` and its reason: the member and the rule |
| 4 | the router itself failed: any other exception while its code is imported and its data loaded, while it writes a hello or its identity, or while it plans a request it reads | the exception type only: a fault in the router's own code (or a broken install), never in the input or the data |

Until round 9's second fix pass (the push check of c4f276c) every exception was exit 2 or 3, so a fault of the router's
own code read as bad data or as bad input. A command line `argparse` cannot read exits 2 with the usage, as in every
`argparse` program.

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
  port; the pool's, `minimum-oversight-floor/pool-2`, in the overseer), computed from the same risk signals: every
  dossier reviewed, two independent instances for a dossier with a repeated fault or a risk signal, and every combined
  answer N_FOLD, its temporary context bounded at 65,536 bytes: exactly in the pool's floor, at most in the service's
  (`minimum-oversight-floor/1` adopts a plan whose merged review's context is bounded lower; holding the bound exactly
  there is a new floor version, the translator's `integration/PROTOCOL.md` section 7a.4, and the service offers no
  combined mode yet). So accuracy never depends on how this router is edited, but for that bound at the service: it can
  add oversight (more duplicates, smaller batches), never remove it, and it never changes a clearance, a delivery or a
  decision. Every plan records this router's identity (name, version, the digests of its rules and of its cost data).

## The data files (`src/epinoic_flash_router/data/`)

| File | What it holds |
|---|---|
| `data/MANIFEST.json` | the current rules and cost-data files, and every data file's version, release and digest |
| `rules-4.json` (current, 0.4.0) | rules/4 in words: the flash decision maker (D1 to D7), the port rules 1 to 7 and the pool rules P1 to P8; the parameters (`max_parts` 16, `max_reviews` 4, `hard_max_instances` 64, `context_max_bytes` 65,536); the pool's thresholds (`escalated_reviewers` 2, `baseline_reviewers` 1, `record_weight` 2, `batch_size` null, `source_reviewers` 1, `merged_reviewers` 1); the decision section (its two approaches, the criterion, the order of the choice, the methods each caller can run); the agreement signals; the features each planner reads; the method table. It is rules/3 with the port's N_FOLD fit-checked: D4 names the pack the system text sizes are of and the merged review no caller divides, D6 and port rule 5 decide the merged review by D4 and D5 and record each part, D7 says where a transfer the service's plan cannot disclose is disclosed |
| `cost-data-4.json` (current, 0.4.0) | the decision maker's prices: 4 characters a token, an output budget of 8,000 tokens, an instance budget of 200,000 tokens, 30 agent-seconds a call and the dossier estimate (planning estimates, not measurements); the system text of every composition of the overseer's knowledge pack 2.1, the pack the overseer sends, as its loader builds it (the core 249,054 characters, with the STEM module 461,507, with the translations module 345,025, with both 557,478) and the dossiers' recorded sizes; no price, no latency, no model |
| `rules-3.json`, `cost-data-3.json` | 0.3.0's rules and prices (the system text of pack 2.0: the core 235,694 characters, with the STEM module 448,147, with the translations module 331,665, with both 544,118), kept byte for byte their 0.3.0 digests |
| `rules-2.json`, `cost-data-2.json` | 0.2.0's rules (with `split_words` 900, the word threshold the fit replaced) and planning estimates, kept byte for byte their 0.2.0 digests |
| `rules-1.json`, `cost-data-1.json` | 0.1.0's rules and cost model, kept byte for byte their 0.1.0 digests |

A digest is the SHA-256 of the document's canonical JSON (keys sorted, no whitespace, non-ASCII raw); the identity
reports the current files' digests. With the released rules the pool plan is the plan the overseer's own planner made
before the decision moved here, for every recorded transfer (the overseer's `test_flash_router_pool.py`), and at pool
port 1.2 each of those plans also carries its decision record. The fast profile is deferred (decision D30).

## Re-tuning and releasing a change

1. Copy the current rules (or cost-data) file to the next version's name (`rules-5.json`), edit it, and try it without
   releasing it: `python -m epinoic_flash_router_cli pool-plan --data <a copy of data/>`, or
   `FlashRouter("<a copy of data/>")`. The plan names the copy's digest.
2. Make it current in `data/MANIFEST.json` with its digest, its version and the release; bump `version` in
   `pyproject.toml` and `__version__` in `src/epinoic_flash_router/__init__.py`; pin the new file's digest in
   `tests/flash_router_tests/test_data.py` (a released file never changes in place). A release names a rules file and a
   cost-data file of its own (the identity test holds both to the release).
3. Run this suite. Nothing in the translator, the engine, the STEM support or the overseer changes, unless the router
   port itself changes (a new port version, agreed with its owner).

When the overseer releases a knowledge pack whose system text differs, the cost data is released again with the new
pack's sizes and names it (`recorded.system_text_pack`): the decision prices every call with the system text the overseer
actually sends, and a pack release that leaves the cost data behind makes a decision record say a dossier fits when it
does not (0.3.0's cost data kept pack 2.0's sizes after pack 2.1, 13,360 characters larger, was installed; 0.4.0
corrected it). This router never imports the overseer, so the comparison of the two belongs to the overseer's tests.

A weakened file (fewer reviewers for an escalated dossier) loads and plans, and the overseer refuses its plans below
the floor (`KIT-RT-020`); the overseer's tests show it on a scratch copy.

## Tests

```
python -m pytest -q          # from this directory: tests/flash_router_tests
```

From the translator's repository root, its documented command (`python -m pytest -q`) runs this suite too, beside the
translator's and the overseer's, and `tests/integration/test_flash_router_subproject.py` runs it once more from this
directory. The suite shows the router port's conformance items over the router-port vectors
(`tests/vectors/router-port/`, copied here by the translator's `integration/tools/vectors.py`; change the kit's
generator, never this copy) and over generated requests, validated with the translator's own
`epinoic_logic.integration.router_port` and `router_pool` (pydantic and the standard library: no engine, no Z3, no
overseer); the pool plans; the data files, their manifest and pinned digests, and the current cost data held to the
system text of pack 2.1 (the dossier of 525,000 characters that cost data 3 recorded as fitting is disclosed
`over_budget`); the runner, its named exit statuses and never a traceback (a request nested 200,000 deep, a number out
of range, a zero quota, a repeated transfer key: exit 3 with the router's own reason; a data file nested too deep: exit
2; a fault of the router's own code: exit 4, never 2 or 3, for nine exception types raised while planning a request it
reads (`ValueError` among them) and seven while loading its data or writing a hello, and for a real fault edited into a
copy of the planner, with no traceback; `test_runner.py`); what the router reads of a request (each refusal with its
exact reason before anything is planned; any request mutated from one in contract planned or refused with a
`RequestError`, never a fault of the router, and answered 0 or 3 by the runner; every pool port 1.2 request the port
accepts planned; `test_contract.py`); determinism in a fresh interpreter; and that the router runs with nothing but its
own `src/` on the path; and the flash decision maker on minimal inputs for each method, risk only escalating, its record
in the pool plan, and the service's combined answer decided as the pool's (three 150,000-character sources: the merged
review recorded `over_budget`, the plan's numbers the record's, a repeated key refused at once, 16,000 sources in one
pass; `test_decision.py`). Inside the translator repository `tests/flash_router_tests/conftest.py` uses its `src/`; a
split copy uses the translator package installed in its environment.

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
