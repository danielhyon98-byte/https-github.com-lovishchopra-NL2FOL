# Overseer-port conformance (`epinoic.integration.overseer-port.v1`)

The overseer is reached only through the port adapter named by `EPINOIC_OVERSEER_PORT` (default
`epinoic_overseer.port`, exposing `connect(config)`); every message it returns is validated by
`integration/overseer_port.py` before it is used (PROTOCOL.md section 6). **The embedded adapter is connected in phase
2**: the overseer package is not on the pre-build branch, and until it is, the service refuses to start with
`KIT-HS-007 overseer_unavailable`.

## The embedded adapter (v1) must

1. answer `hello()` with `port_version 1.0`, `mode embedded`, its auditor version, the exported pack's `PACK_DIGESTS`,
   key ids including `overseer-audit`, `replay_mode process`, `inline_final_release false`, `max_pending_wait_ms` at
   most 250, `agents off|async` and its profiles;
2. build each call's hub with a `TransferAuditor` over a `KeyRing` of the engine key (verify only) and the overseer
   secret's subkeys, `replay_mode="process"`;
3. answer `clearance` from `hub.clearance` and `policy.act_decision`, waiting at most 250 ms, with
   `receipt_sha256` equal to the service's `turn.receipt_sha256(receipt)` (the digest the overseer journals);
4. answer `close` with the FINAL audit from `hub.close_task`, signed under `overseer-audit`, carrying the engine scope
   statement and the TR6 sentence verbatim;
5. answer `deliver` from `hub.consolidate` + `delivery_decision(..., hub=hub)` (single, duplicate) or
   `release_decision` (combined), mapping every reason the overseer gives onto exactly one label of
   `protocol.OVERSEER_REFUSALS` (an unmapped reason is a test failure, never a silent `not_deliverable`);
6. answer `repeats` with the repeated-fault count per transfer key, and `review` with a ticket for the asynchronous
   review under the admitted routing plan: `review` queues the review and returns at once, without waiting for it
   (the review runs after delivery), and its ticket names exactly the admitted plan (`origin`, `plan_id`, `refusal`;
   a ticket for another plan is `KIT-OP-010`). The service calls both after the decision is made: a failure of either,
   or a ticket out of contract, leaves the review unqueued and changes no decision (`tests/integration/test_turn_review.py`);
   it calls them for a call refused before delivery too (the outputs received so far), and not at all for a call
   refused before any output was received (`tests/integration/test_turn_fixes.py`).

What the adapter may rely on, and must not change: the hub's replies name their senders `<slug>-specialist` (with `@a`,
`@b` in duplicate mode; `turn.hub_agent_id`), and a delivery's `deliverable.agent_id` is one of them (the service maps it
back to the protocol id); whatever the adapter raises, `SystemExit` included, the call answers a signed `KIT-DL-900`
verdict (only `KeyboardInterrupt` goes through), so an adapter never ends the service's process; its hello's
`auditor_version` names its release (`0.0.0-test-double` is the simulation's test double, under which every gate of
`integration/sim/run_sim.py` is NOT RUN).

## The suite it must pass

- `tests/integration/test_overseer_port.py` (every message's round trip and every `KIT-OP` refusal) and
  `tests/integration/test_turn_checker.py`, `test_turn_review.py` and `test_turn_fixes.py` with the adapter in place of
  `RecordingPort` (the test double): the same decisions, reasons and refusals on the synthetic corpus;
- `integration/sim/run_sim.py` without `--test-overseer-port`: the service starts with the adapter, and every gate with
  material on the synthetic corpus is judged (`integration/sim/README.md`);
- the overseer's own tampering suite T1 to T22, still naming its expected codes;
- for a **sidecar** (later): the same clearances, audit states, consolidation statuses, delivery decisions and refusal
  reasons as the embedded adapter on every vector, on the simulation corpus and on T1 to T22. Until a sidecar passes,
  the handshake reports `overseer.mode = embedded`.
