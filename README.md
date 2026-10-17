# Epinoic AI flash router (`epinoic-flash-router`)

The flash router decides **how the overseer reviews** each specialist output of a request: one instance reading it whole
(`IN_DEPTH`), the work divided across parallel instances (`SPLIT`), independent duplicate reviews (`DUPLICATE`), or, for
a combined answer, each source reviewed on its own and the combinator's output reviewed against all of them (`N_FOLD`).

It is a **separate, independent agent**: this sub-project has its own `pyproject.toml`, version, rules, cost model and
tests, needs nothing but the Python standard library at run time, and never imports the translator, the engine or Z3.
It is edited, tested and released without touching the Z3 infrastructure. It talks to the translator's service only
through the router port `epinoic.integration.router-port.v1` (the translator's `integration/PROTOCOL.md`, section 7a):

| Function | In | Out |
|---|---|---|
| `epinoic_flash_router.port.hello()` | nothing | one `router-hello.v1` document (JSON text): identity, methods, profiles, `tier: "cheapest"`, `deterministic: true` |
| `epinoic_flash_router.port.plan(request_json)` | one `routing-request.v1` document (JSON text: features only, never an answer or a claim text) | one `routing-plan.v1` document (JSON text) |

## How the service uses it

- **Attached only when named**: `EPINOIC_FLASH_ROUTER=epinoic_flash_router.port`. Unset or `none` (the default):
  detached, and the service runs its minimum-oversight floor for every review. The router is never required.
- **In its own process**: the service runs each call with `python -I`, its own import path and an environment that holds
  no `EPINOIC_` variable (no key, secret or token), for at most 10 s for the hello and at most `min(3 s, what is left of
  the call's budget)` for a plan. Whatever this code does stays in that process.
- **Advisory, under the floor**: everything it answers is validated as untrusted data; a plan out of contract is refused
  with its `KIT-RT` code, a plan below the floor with `KIT-RT-020`, a failing router with `KIT-RT-016`, and the floor
  runs. A plan can add oversight, never remove it, and it never changes a clearance, a delivery or a decision: the
  review it plans runs after delivery.

## What this release plans (rules/1, `src/epinoic_flash_router/rules.py`)

Every transfer gets one entry. The floor's agreement signals (receipt REJECTED, an error-level finding, a repeated
fault, a negative check, a STEM output with an undecided check or `INT-SUBJ-002`) give 2 reviews (`DUPLICATE`); this
router also escalates on a named diagnostic or an unverified dependency (2 reviews), and gives 3 when an agreement
signal and an escalation hold together. A long output read by one review is split into parts of at most 900 words
(`SPLIT`). A combined answer's synthesis is reviewed `N_FOLD` over all its sources with a request-scoped context of at
most 65,536 bytes. Every instance runs on the cheapest tier and on the standard profile when it is offered. Costs come
from a cost model of planning estimates, not measurements, that names no model (decision D23).

The router's identity (name, version, the SHA-256 of its rules and parameters, the SHA-256 of its cost model) is in its
hello and in every plan, so the service's handshake and every verdict's review name the release that planned it.

## Tests

```
python -m pytest -q          # from this directory
```

The suite (`tests/test_conformance.py`) shows the six conformance items of the translator's
`integration/router-port/CONFORMANCE.md` over the router-port vectors (`tests/vectors/router-port/`, copied here by the
translator's `integration/tools/vectors.py`) and over generated requests, validated with the translator's own
`epinoic_logic.integration.router_port` (inside the translator repository, `tests/conftest.py` uses its `src/`), plus
that the router runs with nothing but its own `src/` on the path. The translator's suite runs this suite and the
readiness check of its playbook step 7a on it (`tests/integration/test_flash_router_subproject.py` there).

## Releasing a change

Edit the rules, the parameters or the cost model, bump `version` in `pyproject.toml` and `__version__` in
`src/epinoic_flash_router/__init__.py` (the suite checks they agree), and run the suite. A change of the rules or the
cost model changes the identity's digests by itself. No change to the translator or to the kit is needed, unless the
router port itself changes (a new port version, agreed with its owner).
