# Flash-router conformance (`epinoic.integration.router-port.v1`)

The flash router is a **separate, independent sub-agent** in its own sub-project (`flash-router/`, package
`epinoic_flash_router`), edited and released without touching the Z3 infrastructure. The service never imports it
except through `router_port.attach_router(EPINOIC_FLASH_ROUTER)`, and everything it returns is validated as untrusted
data (PROTOCOL.md section 7a). The planner the overseer rebuild is building moves into that sub-project in phase 2.

## What the sub-project exposes

- `epinoic_flash_router.port.hello() -> str`: one `epinoic.integration.router-hello.v1` JSON document: `port_version`
  `1.0`, the router's identity (`name`, `version`, `rules_sha256` of its rules, `cost_data_sha256` of its recorded cost
  data), the `methods` it plans (a subset of IN_DEPTH, SPLIT, DUPLICATE, N_FOLD), the `profiles` it knows,
  `tier: "cheapest"` and `deterministic: true`.
- `epinoic_flash_router.port.plan(request_json: str) -> str`: one `epinoic.integration.routing-plan.v1` document for
  the `epinoic.integration.routing-request.v1` it is given. Pure: no network, no clock, no randomness, no model call.

It may depend on the translator package only for `epinoic_logic.integration.router_port` (pydantic and the standard
library; no engine, no Z3), the schemas in `integration/schemas/` and the vectors in `integration/vectors/router-port/`.

## What its own tests must show (run them in the sub-project, then playbook step 7a)

1. **Hello in contract**: `router_port.check_hello(hello())` passes; the identity is stable for a release (the same
   `rules_sha256` and `cost_data_sha256` on every call) and changes when the rules or the cost data change.
2. **Round trip**: for every request vector, `router_port.check_plan(plan(request), request, hello=...)` passes, and
   `dump(check_plan(...))` equals the plan it returned (no field dropped, no field added).
3. **Never below the floor**: for every request vector, `router_port.admit_plan(...)` has origin `router` and no
   refusal (`below_floor(plan, floor_plan(request))` is `None`): every transfer reviewed; 2 independent reviews when
   any agreement signal holds; N_FOLD over all sources for a combined answer's output with the bounded context.
4. **Only the request's own data**: a plan carries closed vocabularies only (`REASON_CODES`, `FEATURE_NAMES`), the
   transfer keys of its request, the request's digest and its own identity; never text, an auditor finding, an OVS code,
   a consolidation result, a gold or fault label, or a model (`KIT-RT-011`, `KIT-RT-009`).
5. **Bounded**: at most `min(limits.max_instances, 64)` instances per transfer; `instances = reviews x parts`; totals
   that add up; costs as integers.
6. **Deterministic**: the same request text gives the same plan text.

The kit's own contract tests (`tests/integration/test_router_port.py`) show the other side: every out-of-contract plan
refused with its named code, a below-floor plan refused with `KIT-RT-020` while the floor runs, a router that raises or
returns non-JSON refused with `KIT-RT-016` while the floor runs, and no router at all running the floor.

## What the service guarantees whatever the router does

- The router is never required: absent, failing or out of contract, the floor plan runs and the handshake reports
  `attached: false` with the refusal code.
- Risk signals only escalate: a router can add oversight, never remove it.
- The plan never changes a clearance, a delivery decision or a verdict: the review it plans runs after delivery, off
  the student's critical path, on the cheapest tier.
