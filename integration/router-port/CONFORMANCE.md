# Flash-router conformance (`epinoic.integration.router-port.v1`)

The flash router is a **separate, independent sub-agent** in its own sub-project, [`flash-router/`](../../flash-router/)
(package `epinoic_flash_router`, its own `pyproject.toml`, version, tests and release), edited and released without
touching the Z3 infrastructure. The service reaches it only through `router_port.attach_router(EPINOIC_FLASH_ROUTER)`,
always in a process of its own, and validates everything it answers as untrusted data (PROTOCOL.md section 7a).

## What the sub-project exposes

- `epinoic_flash_router.port.hello() -> str`: one `epinoic.integration.router-hello.v1` JSON document: `port_version`
  `1.0`, the router's identity (`name`, `version`, `rules_sha256` of its rules, `cost_data_sha256` of its cost model or
  recorded cost data), the `methods` it plans (a subset of IN_DEPTH, SPLIT, DUPLICATE, N_FOLD), the `profiles` it knows,
  `tier: "cheapest"` and `deterministic: true`. No name naming a model family.
- `epinoic_flash_router.port.plan(request_json: str) -> str`: one `epinoic.integration.routing-plan.v1` document for
  the `epinoic.integration.routing-request.v1` it is given. Pure: no network, no clock, no randomness, no model call.

At run time it needs nothing but the standard library (the first release imports `json`, `hashlib` and `typing` only).
Its tests may depend on the translator package for `epinoic_logic.integration.router_port` (pydantic and the
standard library; no engine, no Z3); the router-port vectors travel with it in `flash-router/tests/vectors/router-port/`,
copied there by the kit's `integration/tools/vectors.py` (drift-tested).

## What its own tests must show (`cd flash-router && python -m pytest -q`, then playbook step 7a)

1. **Hello in contract**: `router_port.check_hello(hello())` passes; the identity is stable for a release (the same
   `rules_sha256` and `cost_data_sha256` on every call) and changes when the rules or the cost data change.
2. **Round trip**: for every request vector, `router_port.check_plan(plan(request), request, hello=...)` passes, and
   `dump(check_plan(...))` equals the plan it returned (no field dropped, no field added).
3. **Never below the floor, always adopted**: for every request vector (and for generated requests),
   `router_port.admit_plan(...)` has origin `router` and no refusal (`below_floor(plan, floor_plan(request))` is
   `None`): every transfer reviewed; 2 independent reviews when any agreement signal holds; N_FOLD over all sources for
   a combined answer's output with the bounded context. `check.py --router` treats any refusal as a BLOCKER, with its
   code, although in service the floor would run.
4. **Only the request's own data**: a plan carries closed vocabularies only (`REASON_CODES`, `FEATURE_NAMES`), the
   transfer keys of its request, the request's digest and its own identity; never text, an auditor finding, an OVS code,
   a consolidation result, a gold or fault label, or a model (`KIT-RT-011`, `KIT-RT-009`).
5. **Bounded**: at most `min(limits.max_instances, 64)` instances per transfer; `instances = reviews x parts`; totals
   that add up; costs as integers.
6. **Deterministic**: the same request text gives the same plan text (in a fresh interpreter too).

The first release (`flash-router/tests/test_conformance.py`) shows all six, over the vectors and over generated
requests, plus that it runs with nothing but its own `src/` on the import path. The kit runs that suite and the
readiness check on it (`tests/integration/test_flash_router_subproject.py`).

The kit's own contract tests (`tests/integration/test_router_port.py`, `test_router_isolation.py`) show the other side:
every out-of-contract plan refused with its named code, a below-floor plan refused with `KIT-RT-020` while the floor
runs, a router that raises, exits, hangs, or answers with anything but JSON text refused with `KIT-RT-016` while the
floor runs, and no router at all running the floor.

## What the service guarantees whatever the router does

These cover the router's code, not only its return values, because the code never runs in the service:

- **Own process.** `python -I` with the service's import path and an environment holding only `PATH`, the locale, `TZ`
  and the temporary-directory variables (`router_port.CHILD_ENV_NAMES`): no `EPINOIC_` variable, so no key, secret or
  token is in the router's own environment. A patch of the kit's modules (the floor, the admission) changes only the
  router's own process.
- **A fault boundary, not a sandbox.** The router's process runs as the service's user. Before it starts one, the
  service marks itself non-dumpable on Linux (`router_child.protect_service`), so a router without root and without
  `CAP_SYS_PTRACE` cannot read the service's environment or memory; if Linux refuses, no router process starts
  (`KIT-RT-016`). The hosted profile attaches a router only where that holds (`router_child.boundary_problem`: Linux, not
  root, no `CAP_SYS_PTRACE`). Nothing hides the files or other processes of the service's user from the router, so a
  router is installed only as code trusted with that user (decision D28).
- **Bounded.** At most 10 s for the hello at start-up; at most `min(3 s, what is left of the call's budget)` for a plan;
  at most 1 MiB of answer. On a timeout the router and the processes it started are killed. With no time left the
  router is not asked.
- **Contained.** Whatever it raises (`SystemExit` and `KeyboardInterrupt` included), however it exits, whatever it
  prints: the service sees an exit status or an answer text, refuses every failure with `KIT-RT-016` and runs the floor.
- **Never required**: absent, failing or out of contract, the floor plan runs and the handshake reports
  `attached: false` with the refusal code (none when no router is configured).
- **Only escalation**: a router can add oversight, never remove it; risk signals only escalate.
- **Never a decision**: the plan never changes a clearance, a delivery decision or a verdict's decision; any failure of
  the review leaves it unqueued; the review itself runs after delivery, on the cheapest tier.
