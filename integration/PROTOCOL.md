# Integration protocol `epinoic.integration.v1` (normative)

The protocol by which the website (a Cloudflare Worker), the specialist runtime of the agents repository, the
translator's checks service (the Z3 engine, the STEM front end and the branch parsers), the overseer and the flash
router work together so that **no specialist answer is shown as checked without the required Z3 and STEM checks**.
Z3 is not optional: there is no mode in which the website releases a specialist answer without a verdict of this
service, and a missing required part fails loudly with a named code (section 12).

Results prove properties of the logic encoding only. Every verdict carries the engine scope statement and the
overseer's audit scope sentence verbatim (appendix A). A non-success status is never shown as success.

Five ports, each with its own version and closed messages:

| Port | Messages | Required | Section |
|---|---|---|---|
| specialist port `epinoic.integration.specialist-answer.v1` | the runtime's frozen result, wrapped | yes | 4 |
| checks port `POST /v1/turns/check` | `turn-check.v1` in, `turn-verdict.v1` out | **yes** | 5 |
| overseer port `epinoic.integration.overseer-port.v1` | hello, clearance, FINAL audit, delivery decision, review ticket | **yes** | 6 |
| combinator port `epinoic.integration.combinator-port.v1` | synthesis input; output or named refusal; combinator hello (the combinator a separate agent) | combined mode only | 7 |
| flash-router port `epinoic.integration.router-port.v1` | routing request, routing plan, router hello (the router in its own process) | never required (advisory) | 7a |

Machine-readable forms: the pydantic models in `src/epinoic_logic/integration/` (`protocol.py`, `overseer_port.py`,
`combinator_port.py`, `router_port.py`), the JSON Schemas generated from them in `integration/schemas/`, and the golden
vectors in `integration/vectors/`. Where this text and a model disagree, the model and its tests decide, and the
disagreement is a defect of this text.

---

## 1. Conventions

- **JSON shape.** Every message is a JSON object with a closed key set, identified by `schema` (for example
  `epinoic.integration.turn-verdict.v1`) and by `protocol: "epinoic.integration.v1"`. Parsing is strict: UTF-8 only,
  no NaN or Infinity, no duplicate keys, no lone surrogate, nesting at most 64 levels.
- **No floats.** No float appears in any object that is digested or signed: integers and strings only, integers within
  `Number.MAX_SAFE_INTEGER`.
- **Timestamps** are RFC 3339 in UTC and end in `Z`.
- **Canonical JSON.** Keys sorted by Unicode code point; separators `,` and `:` with no whitespace; non-ASCII written
  raw; lone surrogates refused. It is byte-identical to the translator's `ir.canonical.canonical_json` on every value
  the protocol accepts (`canonical.py`; `website/src/verify/canonical-json.js`; vectors `vectors/canonical/`).
- **Digests** are lowercase hex SHA-256: of the canonical JSON for an object, of the exact UTF-8 bytes for a text.
- **Ids** match `^[A-Za-z0-9._:-]{1,128}$`. **Agent ids** match `^(?:[a-z0-9]+(?:-[a-z0-9]+)*(?:@[ab])?|synthesis)$`.
- **Headers:** `Authorization: Bearer <token>`, `Content-Type: application/json`, `Epinoic-Protocol: integration.v1`,
  and `X-Request-Id` (the website's `requestId`, a log label only, never part of a binding).
- **Versioning.** A receiver refuses an unknown major version. A minor version only adds optional fields and announces
  them in the capabilities. Fields are never removed within a major version; codes are never renamed or reused.

## 2. Identifiers

| Protocol id | Website source | Why |
|---|---|---|
| `task_id` | `turnId` (made by the server, stable across the turn's retries and re-arms) | `requestId` changes on every retry and replay; `clientTurnId` is made by the client |
| `request_id` | `attemptId` (new at each admission or re-arm) | each attempt's checks are distinct and fenced |
| `plan_id` | `plan-` + `request_id` | |
| `report_id` | `rep_<task_id>_<agent>_v<n>` (`@` written `-`) | inside the 128-character cap |
| `agent_id` | the agents slug (`history`); `<slug>@a` and `<slug>@b` in duplicate mode; `synthesis` for a combined answer | `WorkPlan` agent ids are distinct |

The identifier mapping is decision D11 (`DECISIONS.md`). **Inside the hub** each answer's specialist is named
`<slug>-specialist` (`<slug>-specialist@a`, `@b` in duplicate mode; `turn.hub_agent_id`), as the arena names it, so the
hub's credit rules read "the History specialist" in an answer as that agent (`adapters.sources.specialist_names`); the
verdict names every answer and the deliverable by its protocol `agent_id`.

## 3. Readiness: five checks that refuse to start or to proceed

Each check refuses with a named code (section 12). None of them ever falls back to an unchecked answer.

**Check 1, when the service starts** (`python -m epinoic_logic.integration serve`, or `epinoic-logic serve` with
`EPINOIC_PROFILE=integration` or `integration-sim`):

- *Bootstrap without engine imports.* `integration/bootstrap.py` uses the standard library only. It checks that the
  `z3` module can be found, that the installed `z3-solver` version is inside the range of `COMPATIBILITY.json`, and
  that `import z3` and a one-line problem succeed. Any failure prints the single line `KIT-HS-003 z3_unavailable` and
  exits with status 2, before any engine module is imported, with no traceback. `integration/__init__.py` imports
  nothing; `cli.py` imports the engine lazily, inside the commands that need it, so `epinoic-logic serve` reaches the
  bootstrap too.
- *Preflight* (`integration/preflight.py`), before a socket is bound, in this order: the profile (012), the component
  versions (002), the STEM branches and the `nonlinear` policy (005), the named policies of contract 0.3 (006), the
  credentials (008), the overseer port and its pinned pack digests (007), the translation provider (009), the subject
  map (010), the specialist contracts (011), the environment (012), the limits (013) and the timing figures (016). The
  first missing part prints one line `KIT-HS-0xx <name>: <detail>` with no secret and exits with status 2. The flash
  router and the combinator are reported, never refused. A profile that is none of `engine`, `integration` and
  `integration-sim` (a misspelled `EPINOIC_PROFILE`) is refused the same way (`KIT-HS-012`) by both entry points, so it
  never starts the plain service in its place.
- *Self-test* (`integration/selftest.py`): three fixed problems decided by the real engine under their named policies
  (a linear entailment under `linear`, a worked STEM step under `nonlinear`, a cross-agent consistency check under
  `joint`). Each must give its expected status and its pinned build-independent digests, a consistent binding and a
  signature that verifies; otherwise `KIT-HS-004`.
- The default profile, `engine`, keeps today's behaviour exactly and adds no route.

**Check 2, every capabilities request** (`GET /v1/capabilities`, authenticated): the service returns
`epinoic.integration.capabilities.v1` (`protocol.Capabilities`): `service_env`, the component `versions` (ir, engine,
policy, translator, z3, contract), the `build` identity (recorded, never required to match), the `selftest` (passed and
its three binding digests), the `ports` (specialist pairs; checks modes, named policies and STEM branches with
`report_budget_max_s`; the overseer's mode, auditor version, pack digests, `replay_mode: process`,
`inline_final_release: false`, agents and profiles; the translation provider and `tier: cheapest`; the combinator's
availability; **the router: `required: false`, `attached`, its `identity` (name, version, rules digest, cost-data
digest) or the refusal code of its hello, and the floor's name and rules digest**), the `subject_map` version and
digest, the `policies`, the `limits`, the `signing` key ids (never keys) and `issued_at`.

**Check 3, in the Worker before admission: the configuration** (`verification.configProblem()`, synchronous): the
simulation switch `KIT_SIMULATION` is set only in local development (`APP_ENV` `development`; on `staging`,
`production` or any other environment it is `simulation_on_hosted`, and it never turns a hosted Worker's environment
label into `sim`); `TRANSLATOR_MODE` is `http` or `binding`; the base URL is https (http only on loopback); the token is
present and well formed; the binding is present in `binding` mode; an inner orchestrator exists; the timing invariant
holds for the base's deadline. Otherwise 503 `chat_unavailable` before admission (nothing stored or charged), logged
only as the label `kit_config:<problem>`.

**Check 4, in the Worker after admission and before routing: the handshake** (`await verification.ready({signal})`):
a capabilities response fetched less than 60 s ago by this verification object (one GET, 3 s timeout; the handler
makes one object per request, so each turn that is not a replay fetches once) that matches the pinned
compatibility set and reports `selftest.passed`; development and `sim` accept the fixture provider, staging and
production require a live provider. Replays never reach this check. On failure the attempt fails with
`kit_hs_not_ready`, `kit_hs_unreachable` or `kit_hs_mismatch` (POST 503 `service_unavailable`, retryable) and no
classifier, specialist or checks call is made. The same rules are stated in `integration/handshake.py` and
`website/src/verify/verification.js` on the vectors `vectors/handshake/`. **The router's absence changes nothing.**

**Check 5, in the Worker after routing and before the specialist call: the subject.** The routed website route maps
to a slug of the subject map for this environment, and the runtime reports that slug available (its own
`getCapabilities` answer, `epinoic.specialist-capabilities.v1`: an entry of `entries` with that slug and
`available: true`; an answer of any other shape lists no specialist); otherwise `specialist_unmapped` or
`specialist_unavailable` (503 `chat_unavailable`). There is never a fallback to another
specialist and never a fan-out.

## 4. Specialist port (`epinoic.integration.specialist-answer.v1`)

The port wraps the runtime's frozen result and never changes it.

| Field | Content |
|---|---|
| `schema`, `protocol`, `agent_id` | as above |
| `runtime` | `{schema: result.schema, contract_version: result.contractVersion}`, one of the accepted pairs: result `epinoic.specialist-turn-result.v1` with runtime `epinoic.specialist-runtime.v0.1.0`, result `.v2` with runtime `v0.2.0` |
| `log` | the runtime's own `redactForLog(result)` (log schema v1 or v2, matching the result) **without its `turn` and `usage` members**: the website's conversation id never leaves the Worker |
| `answer` | `result.answer`, unchanged (at most 49,152 UTF-8 bytes) |
| `answer_sha256` | SHA-256 of the answer's UTF-8 bytes |
| `result_sha256` | SHA-256 of the canonical JSON of the whole frozen result, computed in the Worker; opaque to the service |

Rules, checked in this order by the service (`specialist_port.check_answer`) and mirrored by the Worker
(`specialist-port.js`): shape (KIT-REQ-001); a self-certification key at the top level (005); the result schema and
the runtime contract (010, 011); the log projection of that schema without `turn` and `usage` (010, 011, 001); the
outcome `answer` (012); the runtime gate `passed` (013); `provenance.claims` is null (011: claims are extracted by the
translator's parsers, never by the runtime); the size (006); the answer digest (014); the slug of the subject map (015).
An envelope is built only for the outcome `answer`; every other outcome maps to the website's own closed error without
a checks call. A gate pass is a format precondition, never evidence of verification (appendix A).

## 5. Checks port (required): `POST /v1/turns/check`

### 5.1 Request (`epinoic.integration.turn-check.v1`)

| Field | Rule |
|---|---|
| `mode` | `single`, `duplicate` or `combined`, one of `capabilities.ports.checks.modes`. Single takes 1 answer; duplicate and combined take 2 |
| `ids` | `{task_id, request_id}` |
| `task` | `{route, slug, subject, course_level, task_type, user_text, user_text_sha256, supplied_texts}`; route, slug and subject are one row of the subject map for the service's environment; `user_text` at most 49,152 UTF-8 bytes |
| `answers` | specialist envelopes (section 4); agent ids `slug`, or `slug@a` and `slug@b`, or two different mapped slugs |
| `policy` | `verified-v1` (default) or `verified-v1-qualify`: a name, never limits or a free-form object |
| `budget_ms` | between `checks_min_ms` and `checks_max_ms`; the Worker computes it from the turn's deadline |
| `revision_of` | a `verdict_id`, or `null` |

The request passes the service's existing gates unchanged: bearer authentication (401 E502), the per-token rate limit
(429 E503), the body limit read before the body (413 E306), strict JSON with a closed key set (400 E100),
self-certification (400 E505) and non-blocking concurrency (503 E504). A request that passes them and is out of the
protocol's contract is answered 400 `{code: KIT-REQ-0xx, message, request_id}`, and nothing runs.

### 5.2 Processing order inside the service (normative; `integration/turn.py`)

One call uses one fresh hub from the overseer port (`new_hub`: a `RouterHub` with a `TransferAuditor`,
`replay_mode="process"`):

1. validate the envelope and the answers (`checks_port.check_request`; KIT-REQ codes);
2. build and seal a `WorkPlan` (subject from the subject map, the answers' agent ids, `agent_subjects` in combined mode,
   `deadline_at` = now + budget);
3. open the task and dispatch the student's message to each agent; check the **clearance** of each dispatch receipt
   before acting (a REJECTED dispatch is an integrity failure);
4. prefetch translations (live providers only; section 5.3);
5. receive each answer as raw text with its agent id and report id (the branch parser extracts the claims); the STEM
   front end runs with `min(STEM_CHECK_BUDGET_S, budget left)`; check the clearance of each response receipt before
   acting (at most 250 ms of waiting);
6. combined mode only: the combinator port's synthesis, relayed through the hub, with its own clearance;
7. `close`: the FINAL audit, signed under `overseer-audit`;
8. `deliver`: `consolidate` then `delivery_decision` (single, duplicate), or `release_decision` (combined);
9. the per-claim entries of the deliverable, the counts over all its claims, and the decision table (section 8) under
   the named policy: **the decision is made here, and nothing after this step changes it**;
10. when the asynchronous overseer-agent review is enabled: build the flash router's request, ask the router, in its
    own process, for a plan within what is left of the budget and at most 3 s (`router_port.PLAN_TIMEOUT_S`), admit
    the plan against the floor (section 7a) or run the floor, and hand the review to the overseer port, which queues it
    and returns. Any failure of this step (the router; the port's `repeats` or `review`; a ticket out of contract or
    for another plan) leaves the review unqueued (`overseer.review.queued: false`), is recorded in the evidence, and
    changes neither the decision nor its reasons; the review itself runs after delivery and is never a release
    condition. Then sign the verdict (HMAC-SHA256 under the verdict key, never the engine key);
11. `integration-sim` profile only: write the call's evidence to the evidence tap (section 5.5).

**A call refused before step 9** (an integrity failure at a clearance, for example) still has step 10: its review is
planned and queued over the outputs received so far, and the decision is the one without a review. A call refused
before any output was received has nothing to review: the review is not queued and its evidence says why.

**Budget.** One monotonic deadline covers steps 3 to 9. Once it has passed the verifier returns no outcome for the
remaining claims: each eligible claim left so becomes `NOT_ATTEMPTED` with `skipped_budget`; STEM checks left over
(`INT-SUBJ-002`) become `NOT_ATTEMPTED` with `stem_budget`. Step 10 only uses what is left of the same deadline (with
none left the router is not asked: `KIT-RT-016`, the floor runs), so the review never makes a verdict later than its
budget and the Worker's timeout (budget plus `checks_tail_ms`) is never spent on it. **An unexpected exception yields a signed verdict whose
decision is `refuse_incomplete` with reason `KIT-DL-900`, never `deliver`**: any exception an adapter raises, `SystemExit`
included (only `KeyboardInterrupt` goes through); in step 10 the same leaves the review unqueued and changes neither the
decision nor its reasons. Every message the overseer port returns is
validated before it is used; an out-of-contract message is never acted on.

### 5.3 Cheapest-tier translation

- **Live providers** (`anthropic`, `openai_compatible`; the model id is the owner's configuration, decision D23): a
  task-aware verifier `fn(claim, report, task=...)` over the translator's own provider classes, the claim cap
  `max_translated_claims` (8), and `PrefetchingProvider`, which serves first-attempt proposals from a cache filled in
  parallel (at most 4 in flight) and keyed by the exact first-attempt request. Non-interference: receipts are
  identical with the prefetch on and off. No live provider call has been made or evidenced.
- **Fixture provider** (development and `sim`): `FixtureCorpus` serves a corpus in the arena round format, each item
  found by the SHA-256 of its recorded answer and each fixture bound to its claim by claim id and claim-text digest
  (a fixture bound by claim id only is refused at load time). It serves exactly what `scripts/arena/run_arena.py`
  serves for the same item, called as `fn(claim, report)` without a task, as the arena calls its verifier. A fixture
  recorded under the arena's request id of its item (`req-<item>`, or `req-<group>`) is served under the request id
  of the claim it translates (`RekeyingFixtureProvider`; a no-op in the arena); a fixture recorded for another request
  is served as it is, and the pipeline refuses it as the arena does (INVALID_FORMALIZATION).
- **Fidelity review** (decision D6) is off: `release_permitted` is false, so a positive formal result is labelled a
  formal check of the encoding, never "checked", and an answer's badge says at most "Partly checked (encoding only)",
  never "passed" (section 8).

### 5.4 Response (`epinoic.integration.turn-verdict.v1`; `protocol.TurnVerdict`)

```
{ schema, protocol, verdict_id, issued_at,
  ids: {task_id, request_id, plan_id, channel_uid},
  bound: {user_text_sha256, policy, mode, answers: [{agent_id, answer_sha256, result_sha256, report_id, message_id}]},
  service: {service_env, versions, build, subject_map_sha256},
  delivery: {decision: deliver|revise|refuse_unresolved|refuse_incomplete|refuse_integrity,
             deliverable: {agent_id, answer_sha256, message_id} | null, reasons: [KIT-DL-*],
             consolidation: {id, status, basis} | null, synthesis: {id, receipt_status} | null},
  overseer: {mode, final_audit_id, state, error_codes: [OVS-*], delivery_allowed, refusal: closed label | null,
             review: {queued, plan_origin: router|floor|null, plan_refusal: KIT-RT-*|null, router: identity|null}},
  receipt: {status, error_codes, warning_count, branch},
  claims: [{claim_id, materiality, role, excerpt, source: translation|branch_check|stem, formal, attempt, fidelity,
            evidence_resolved, release_permitted, result_id, binding_digest}]   (at most 32, material first),
  counts: {claims_total, material, eligible, attempted, definitive, positive, permitted, blocking, unavailable, not_eligible,
           budget_skipped},
  summary: formally_checked|partly_checked|formal_only|not_formally_checkable|incomplete | null,
  scope_statement, audit_scope_statement, timings: {total_ms, translation_ms, solver_ms, overseer_ms},
  signature: {alg: "hmac-sha256", key_id, value} }
```

`receipt` and `claims` describe the deliverable (single: the answer; duplicate: the representative; combined: the
synthesis). `excerpt` is a verbatim part of the deliverable of at most 200 characters. `counts` cover **every** claim
(the list is capped at 32, material first, and a claim without an excerpt is counted but not listed), so the Worker
re-derives the decision and the summary exactly from them, and checks them against the list: every listed count is a
lower bound of its count whatever the list's length, every count is exact when every claim is listed and every count
but `claims_total` when every material claim is, and the counts must be those of some list of claims
(`delivery.counts_problem`, `release-gate.js countsProblem`). A listed material claim that is TIMEOUT or
COUNTEREXAMPLE can therefore never be counted away. `budget_skipped` counts the material eligible claims the budget or
the STEM budget left `NOT_ATTEMPTED` (attempt `skipped_budget` or `stem_budget`), at most `unavailable`; the service
names `KIT-DL-013` from it, over every claim, and the Worker re-derives the same reasons from the same count, so a
budget skip outside the listed claims (beyond the first 32, or without an excerpt) is never dropped. `summary` is set only for
`deliver`. The overseer's `refusal` is one closed label: `clearance_failed`, `clearance_pending`,
`final_audit_not_passed`, `signature_invalid`, `custody_failed`, `stale`, `consolidation_conflicting`,
`no_deliverable_output`, `receipt_error_findings`, `not_deliverable`, or `internal_error` (the service's own label for
the KIT-DL-900 verdict). No response carries the evidence bundle.

**Signature scope.** The Worker holds no key (decision D12): it trusts the authenticated channel, checks the bindings
and re-derives the decision; it never claims to have verified the HMAC. The signature lets operators and the overseer
audit the verdict later.

### 5.5 The evidence tap (`integration-sim` only)

`EPINOIC_SIM_EVIDENCE_DIR/<request_id>.json` holds each call's full evidence (receipts, outcomes, signed results, the
FINAL audit, the delivery decision, the routing admission and the verdict) so the simulation compares the website-path
call with the reference harnesses. Every other profile, and a non-loopback bind, refuses it (`KIT-HS-012`).

## 6. Overseer port (`epinoic.integration.overseer-port.v1`; `integration/overseer_port.py`)

The overseer is reached only through this port, which is what lets it be a separate sub-project. The service loads the
adapter module named by `EPINOIC_OVERSEER_PORT` (default `epinoic_overseer.port`, exposing `connect(config)`) and
validates everything it returns as untrusted data. Anything that prevents a connection is `KIT-HS-007`.

| Operation | Embedded mode (v1) | Message |
|---|---|---|
| `hello` | auditor version, the exported pack's digests, key ids (with `overseer-audit`), replay mode | `overseer-hello.v1` |
| `new_hub` | a `RouterHub` with a `TransferAuditor` (a `KeyRing` of the engine key and the overseer secret's subkeys) | (object) |
| `clearance` | `hub.clearance` and `policy.act_decision` before every action, waiting at most 250 ms | `overseer-clearance.v1` |
| `close` | `hub.close_task`: the FINAL audit, signed under `overseer-audit` | `overseer-final-audit.v1` |
| `deliver` | `hub.consolidate` + `delivery_decision(..., hub=hub)`, or `release_decision` for a synthesis | `overseer-delivery.v1` |
| `view`, `repeats` | the authoritative journal view; repeated-fault counts per transfer key | (data) |
| `review` | the asynchronous overseer-agent review under the admitted routing plan | `overseer-review-ticket.v1` |

Refusals (`KIT-OP`): 001 malformed, 002 port version, 003 no pinned pack digest, 004 replay mode other than `process`,
005 an inline-replayed FINAL audit offered for release, 006 an unknown audit state, 007 `may_act` for a state that is
not passed or with error-level findings, 008 an `OVS-AGENT-*` code in a clearance or audit state, 009 an audit without
the scope statement and the TR6 sentence, 010 a message for another transfer, task or audit, 011 an inconsistent
decision (allowed without a deliverable, refused without a label, a non-deliverable consolidation, a release decision
about anything but the synthesis), 012 no `overseer-audit` signature.

Trust rules carried over unchanged: only deterministic `OVS-*` findings affect clearance; `OVS-AGENT-*` never changes a
clearance; the auditor holds engine keys only to verify and signs under its own subkeys; every audit carries both scope
statements; overseer agents are built only from the exported pack and their verdicts are validated, never obeyed; the
simulation's language-model adjudicator that could clear a formal error is not part of the integrated overseer
(decision D18). Agent reviews run after delivery and never retract a delivered answer (decision D22).

**Sidecar mode** (later) replaces the embedded adapter only after passing `integration/overseer-port/CONFORMANCE.md`.
Until then the handshake reports `overseer.mode = embedded`.

## 7. Combinator port (combined mode only; `epinoic.integration.combinator-port.v1`; `integration/combinator_port.py`)

The combinator turns the delivered claims of a combined answer's specialists into one synthesis. It is a **separate
agent in its own sub-project** (`combinator/`, package `epinoic_combinator`, its own `pyproject.toml`, version,
instructions and tests; standard library only at run time), edited and released without touching the Z3
infrastructure. The translator never imports it: the service reaches it only through this port and treats everything
it returns as untrusted data. **The hub stays the independent checker of every synthesis**: a port check is a contract
check, never a faithfulness check (`integration/combinator-port/CONFORMANCE.md`).

| Message | From | Content |
|---|---|---|
| `combinator-input.v1` | service | the request's ids; per delivered report its id, agent, subject, branch and every claim (id, role, materiality, certainty, text and the SHA-256 of the text; `combinator_port.build_input`, `source_report`); the closed vocabulary; the instruction pack the service pins (`PackRef`) |
| `combinator-output.v1` | combinator | the synthesized claims (text, cited source claim ids, certainty, one transformation of the vocabulary, optional evidence references), the dropped ledger (source claim ids and a reason) and the disclosed `conflicts` (two distinct source claim ids at least and a neutral description), the request's ids and the pack's digest. The combinator's own texts (a claim's text, a reason, a description) are words: at least one visible character, no control character but a tab or a line break, no bidirectional embedding, override or isolate (`combinator_port.TEXT_PATTERN`) |
| `combinator-refusal.v1` | combinator | no output in contract: a closed `reason` with its one `KIT-CB` code (`combinator_port.REFUSAL_REASONS`), the request it refuses (null only when the input could not be read, or for an internal error before it was), the pack's digest and a detail that never echoes the agent's prose |
| `combinator-hello.v1` | combinator | its release (name, version), the instruction pack it runs, the digest of the published contract it validates against (`contract_sha256`), `tier: cheapest` and the vocabulary; no name naming a model (D23) |

**The published contract** is those four JSON Schemas, the synthesis contract's closed vocabularies
(`schemas/synthesis-vocabulary.v1.json`, built from `integrity/contracts.py`: the transformations a synthesized claim may
carry, `carried`, `paraphrased`, `merged`, `narrowed`, `generalized`, with what each records; the certainty order) and the
port's rules (`schemas/combinator-port.v1.json`: the refusal reasons and codes, the limits, the order of the checks).
`integration/tools/generate.py` writes them from the models and copies them into the sub-project
(`combinator/src/epinoic_combinator/contract/`, drift-tested); `combinator_port.contract_digest()` is their digest. Claim
ids use the hub's claim id alphabet (`[A-Za-z0-9._:@-]`, so the generic parser's `g4.2@economics-specialist` is carried).

**Checks** (`check_input`, `check_output`, `check_hello`, `check_refusal`), in this order for an output: not protocol
JSON or not a JSON object (002; a message passed already parsed is held to the same JSON rules as text: a lone
surrogate, a float or a non-string key is not protocol JSON); a synthesized claim's transformation outside the vocabulary (003), before anything else; the schema (a
combinator text out of `TEXT_PATTERN`, blank or holding a control character, included), a
synthesized claim citing a source claim twice (one source cited twice would pass for a `merged` claim) and a conflict
naming a claim twice (002); another request (002); another instruction pack (005); a citation of a claim the
input does not hold, by a synthesized claim, a dropped entry or a conflict (004); a synthesis text over 49,152 UTF-8
bytes (006). Refusals (`KIT-CB`): 001 input malformed, 002 output malformed (and every case without an output in
contract: no provider, a provider that failed or gave no text, an internal error; the refusal's reason tells them apart;
a hello or a refusal out of contract), 003 a transformation outside the closed vocabulary, 004 a source claim the input
does not hold, 005 an instruction pack other than the pinned one, 006 too large.

**The relay.** The service turns a checked output into the `synthesis/1.0` mapping (`combinator_port.synthesis_payload`:
claims `s0`, `s1`, ... never reusing a source claim id; dropped entries as ledger entries `dropped`; disclosed conflicts
as `unresolved` conflict records; the student-facing text the claims' texts joined) and relays it through the hub, whose
contract validation (`INT-REQ-009`, `INT-SYNTH-014`), ledger (`INT-LEDGER-*`, the carried self-report or verification label and a note carried back as a claim
`INT-LEDGER-029` included), conflict disclosure (`INT-CONFLICT-002`, between formalized claims; a contradiction in prose is named only
through the figures it changes, `INT-LEDGER-023`/`024`; a disclosed conflict over claims in which the hub found no
contradiction is `INT-CONFLICT-006`, info: the record is the combinator's statement, not a check) and entailment checks decide
it as untrusted data.

v1: a cheapest-tier provider call with the versioned instruction pack pinned by digest, run by the sub-project's runner.
**Until the combinator is connected (phase 2: `EPINOIC_COMBINATOR` names `epinoic_combinator.port`, its process and
provider credential decided under D33), the capabilities omit `combined` and the checks port refuses it (`KIT-REQ-002`).**

## 7a. Flash-router port (`epinoic.integration.router-port.v1`; `integration/router_port.py`)

The flash router is the oversight planner's decision maker: per request and per specialist output it decides **how
the overseer reviews**. It runs as a **separate, independent sub-agent** in its own sub-project (`flash-router/`,
package `epinoic_flash_router`) that can be edited and released without touching the Z3 infrastructure. It talks to the
service only through this port (JSON text in, JSON text out). It is not the translator's `RouterHub` (which carries
messages between agents) and not the website's subject routing (which picks one specialist).

**Attachment.** The router is attached only when `EPINOIC_FLASH_ROUTER` names its module (`epinoic_flash_router.port`
for the sub-project); unset, empty or `none` (the default, decision D28) detaches it and the floor runs. The module
exposes `hello() -> str` (`router-hello.v1`) and `plan(request_json: str) -> str` (`routing-plan.v1`).

**The router runs in its own process, never in the service's** (`router_port.run_router`, `router_child.py`): for each
call the service starts `python -I` with its own import path and an environment holding only `PATH`, the locale, `TZ`
and the temporary-directory variables (`router_port.CHILD_ENV_NAMES`: no `EPINOIC_` variable, so no key, secret or
token is in the router's own environment), writes one job to its standard input and reads the router's answer, written
only by the runner, from its standard output: at most 10 s for the hello at start-up (`HELLO_TIMEOUT_S`), at most
`min(3 s, what is left of the budget)` for a plan (`PLAN_TIMEOUT_S`), at most 1 MiB (`MAX_ANSWER_BYTES`). Whatever the
router's code raises, however it exits, whatever it prints and whichever kit module it patches stays in that process:
it cannot change the floor or the admission, or raise into the service; on a timeout it is killed with its own
children. Not configured: detached, no refusal. Configured but not importable, or failing its hello: detached with
`KIT-RT-016`; without `hello()` and `plan()`, or with a hello out of contract: detached with `KIT-RT-015`. The service
starts either way.

**A fault boundary, not a sandbox.** The router's process runs as the service's user and can do what that user can do
(read its files, signal its processes, use the network). What keeps the service's keys out of its reach: before it
starts any router process the service marks itself non-dumpable on Linux (`router_child.protect_service`,
`prctl(PR_SET_DUMPABLE, 0)`), so a router without root and without `CAP_SYS_PTRACE` can read neither the service's
environment nor its memory (`/proc/<pid>/environ`, `/proc/<pid>/mem`, `ptrace`); when Linux refuses, no router process
starts (`KIT-RT-016`). This does not hold for a service that runs as root or with `CAP_SYS_PTRACE` (its router gets the
same power), on another system, or for secrets kept in files or in other processes of the same user
(`router_child.boundary_problem`). So **the hosted profile `integration` attaches a router only where it holds** (Linux,
not root, no `CAP_SYS_PTRACE`; otherwise detached with `KIT-RT-016` before any router process starts), keys and tokens
come from the service's own environment only, and a router is installed only as code trusted with the service's user
(decision D28). The loopback simulation (`integration-sim`, ephemeral test keys) and `check.py --router` attach it
anyway and claim no secret boundary.

### 7a.1 Methods (per transfer)

| Method | Meaning | Independent complete reviews |
|---|---|---|
| `IN_DEPTH` | one overseer instance examines the whole response | 1 |
| `SPLIT` | the work divided across several parallel instances (`parts`, at most 16), each part reviewed once | 1 |
| `DUPLICATE` | independent duplicate reviews of the whole response (`reviews` 2 to 4), combined by the verdict combination | `reviews` |
| `N_FOLD` | combined answers only: each specialist's individual response reviewed by its own entry before combination, then one merged review of the combinator's output naming exactly the N sources, with a request-scoped temporary context of the per-source validated outcomes (at most 65,536 bytes, discarded after the request) | `reviews` |

`instances` = `reviews` × `parts` per transfer, at most `min(limits.max_instances, 64)`. Every instance runs on the
cheapest tier; the profile is `standard` or `fast` from the overseer's hello. A plan never names a model.

### 7a.2 The routing request (`routing-request.v1`; built by `integration/routing_features.py`)

Features only, never text:
- **request**: subjects; STEM or not; task type and course level; request items (`item_id`, kind, required, command
  term, level) and constraints (`constraint_id`, kind, value digits only); supplied texts by document id, digest and size;
  the student text's digest;
- **per output** (one per transfer, keyed by its message id): role (`answer` or `synthesis`), agent id, subject, branch,
  STEM; size (characters, words, paragraphs); claims (total, material, eligible, translated); the engine statuses of its
  claims and checks (counts per status); the receipt's status, error codes and warning codes; the named diagnostics
  (codes; connected in phase 2); unverified dependencies; peer relays; repeated faults (from the overseer port);
- **topology**: `single`, `duplicate`, or `combined` with its N sources and its synthesis;
- **limits**: `max_instances` and the profiles the overseer offers.

A request that carries anything a blind dossier hides (an auditor finding, a consolidation result, an OVS code, a gold
or fault label, any text) is refused (`KIT-RT-011`).

### 7a.3 The routing plan (`routing-plan.v1`)

`{schema, protocol, port_version, origin: "router", plan_id, ids, request_sha256, router: {name, version,
rules_sha256, cost_data_sha256}, transfers: [{transfer_key, method, reviews, parts, instances, profile, tier,
sources, context, reasons, features_used, estimated_cost: {tokens, seconds} | null}], totals: {instances,
estimated_cost}}`. `reasons` and `features_used` are closed vocabularies (`REASON_CODES`, `FEATURE_NAMES`): a plan
carries no free text. `risk_diagnostics` and `risk_unverified_dependencies` name escalations a router may add on
features the floor does not read. `router` must equal the identity of the router's hello. No member names a model,
and neither the `plan_id` nor a router name names a model family (`router_port.MODEL_FAMILIES`).

### 7a.4 The minimum-oversight floor (`minimum-oversight-floor/1`; its rules and digest are `FLOOR_RULES`)

**The plan is advisory; the floor is enforced.** The overseer computes the floor deterministically from the same risk
signals the router reads:
1. every transfer of the request is reviewed;
2. a transfer gets at least **2** independent complete reviews when any agreement signal holds: its receipt is
   REJECTED; it carries an error-level finding; it carries a repeated fault; a material or branch check is
   COUNTEREXAMPLE, INCONSISTENT_PREMISES or UNSATISFIABLE; it is STEM and a check is UNKNOWN, TIMEOUT, INTERNAL_ERROR or
   NOT_ATTEMPTED, or its receipt carries INT-SUBJ-002; otherwise at least 1;
3. **a combined answer's floor is N_FOLD** over all its sources, with the bounded temporary context;
4. IN_DEPTH and SPLIT are 1 complete review; DUPLICATE is its number of reviews; the profile is not part of the
   floor; every instance runs on the cheapest tier;
5. the floor plan runs IN_DEPTH or DUPLICATE (2) per transfer and N_FOLD for the combinator's output, standard profile.

**Admission** (`admit_plan`, `route`): no router attached → the floor plan runs (origin `floor`, no refusal). A plan
out of contract → refused with its `KIT-RT` code, the floor plan runs. A plan below the floor → refused with
`KIT-RT-020 below_floor`, the floor plan runs. Otherwise the router's plan runs (origin `router`). So a router can only
add oversight; risk signals only escalate; the review never changes a clearance, a delivery or a verdict's decision.

`minimum-oversight-floor/1` reads neither the named diagnostics nor the unverified dependencies of an output: a router
may escalate on them, the floor does not. A floor that does is a new floor version (`minimum-oversight-floor/2`, its own
rules digest), decided when the argument diagnostics are connected (decision D29).

### 7a.5 Refusals (`KIT-RT`), in the order `check_plan` applies them

Each rule about transfers is applied to every transfer before the next rule, so a plan's code does not depend on the
order of its transfers.

001 malformed; 011 hidden content anywhere in the plan; 009 a model named (a member, or a `plan_id` or router name naming
a model family) or a tier other than `cheapest`; schema errors mapped by location (012 vocabulary, 013 cost, 007 method,
010 profile, 009 tier); 003 origin or identity (the floor's identity is reserved); 002 not bound to this request
(`request_sha256`, ids); 003 an identity other than the hello's;
004 a transfer key the request does not hold; 006 a transfer planned twice; 005 a transfer left unplanned; 007 a method
shape that does not hold (`N_FOLD` only for the synthesis of a combined answer, its sources exactly the topology's,
its context bounded; `SPLIT` with parts; `DUPLICATE` with at least 2 reviews; `IN_DEPTH` 1 × 1) or a method the hello
does not offer; 010 a profile the overseer does not offer; 012 duplicated vocabulary; 013 a missing cost; 008 more
instances than the limit for a transfer; 013 totals that do not add up; then 020 below the floor. Hello refusals: 015
(a hello out of contract, a router name naming a model family, a module without `hello()` and `plan()`); request
refusals: 014 (or 011). **016, the router failed**: a configured module that cannot be imported; a router that raises
(whatever it raises), exits, is killed, does not answer within its time, or answers with anything but JSON text (a
non-text value, text that is not strict JSON, more than 1 MiB); no time left in the budget. JSON that is not an
admissible plan keeps its own code (001 when it is not a plan object at all).

### 7a.6 What the handshake reports

`ports.router`: `required: false`, `attached`, `identity` (name, version, rules digest, cost-data digest) or the
refusal code of its hello, and the floor's name and rules digest. The report is coherent: `attached` exactly when an
`identity` is reported, no `refusal` when attached, and a refusal is one an attachment gives (`KIT-RT-015` or
`KIT-RT-016`, `protocol.ROUTER_ATTACH_REFUSALS`), and no attached router is named by the floor's reserved identity
(`minimum-oversight-floor`, `protocol.FLOOR_IDENTITY_PREFIX`: a router hello naming it is refused with `KIT-RT-015`);
an incoherent report is out of contract and both handshakes refuse it with `KIT-HS-001` (vectors `handshake/router-*`). Every verdict's `overseer.review` names the plan's origin, any refusal
and the router's identity.

## 8. Statuses, the decision table and the website mapping

**Per claim.** Six definitive statuses, verdicts about the encoding only: positive ENTAILED, CONSISTENT, SATISFIABLE;
negative COUNTEREXAMPLE, INCONSISTENT_PREMISES, UNSATISFIABLE. Seven non-results: UNKNOWN, TIMEOUT, UNSUPPORTED,
INVALID_FORMALIZATION, AMBIGUOUS_TRANSLATION, NOT_ELIGIBLE, INTERNAL_ERROR. `NOT_ATTEMPTED` is the kit's marker for an
eligible claim that was skipped (cap, budget, provider unavailable, STEM budget): a non-result.

**Per answer** (`delivery.decide`, `website/src/verify/decision-table.js`; vectors `vectors/decision-table/`). Rows in
order, first match wins; only material claims count where a row says so:

| # | Condition | Decision | Reasons |
|---|---|---|---|
| 0 | the service's own internal-error verdict (refusal `internal_error`) | `refuse_incomplete` | KIT-DL-900 |
| 1 | (Worker) the binding checks fail: shape, ids, user text, policy, mode, answers, decision re-derivation, counts, summary, excerpts, the released text | `refuse_integrity` | KIT-DL-030 |
| 2 | the receipt is REJECTED; the FINAL audit failed; delivery refused for a clearance, signature, custody or staleness reason, or without a label | `refuse_integrity` | KIT-DL-001, -003, -005, -006 |
| 3 | the clearance is still pending after the bounded wait | `refuse_incomplete` | KIT-DL-004 |
| 4 | error-level receipt findings; a CONFLICTING or NO_DELIVERABLE_OUTPUT consolidation; a material claim COUNTEREXAMPLE, INCONSISTENT_PREMISES or UNSATISFIABLE | `revise` when the policy allows one revision not yet made (no v1 policy does, D5), else `refuse_unresolved` | KIT-DL-002, -007, -008, -010; -020 after a revision |
| 5 | a material eligible claim UNKNOWN, TIMEOUT, INTERNAL_ERROR or NOT_ATTEMPTED | `verified-v1-qualify`: continue; `verified-v1` and any policy the table does not know: `refuse_incomplete` (fails closed) | KIT-DL-011; -013 when the budget was spent |
| 6 | a material claim AMBIGUOUS_TRANSLATION | continue with its label (no v1 policy blocks it, D4) | (KIT-DL-012 reserved) |
| 7 | otherwise | `deliver` | |

NOT_ELIGIBLE, UNSUPPORTED and INVALID_FORMALIZATION neither block nor leave the checks incomplete; they are labelled not
formally checked. **Summary** of a delivered answer, from the counts: `incomplete` (a material eligible claim without a
definitive result, reachable only under the qualify policy); `not_formally_checkable` (no positive result);
`formally_checked` (every material eligible claim positive with `release_permitted`); `partly_checked` (some);
`formal_only` (positive results, none permitted). **A non-definitive status never yields `formally_checked`, whatever
the policy** (property-tested).

**Website mapping** (proposed; decisions D13, D26, D27). A delivered verified answer carries
`review: "checks:integration.v1"` (append-only in `REVIEW_STATES`), never `passed` or `not_required`. **Its badge
follows its `checksSummary`** (`chat-contract.js checksBadge`, vectors `chat-contract/labels.json` `badges` and
`badge_cases`; decision D27, conservative default): "Automatic checks passed" (success tone) only for
`formally_checked`, where every material eligible claim has a positive result whose release is permitted; "Partly
checked" for `partly_checked` and "Partly checked (encoding only)" for `formal_only`, with no success tone, since either
may hold material claims that are not formally checked or positive results of the encoding only; "Not formally checked"
for `not_formally_checkable` (and any unknown summary); "Some checks unavailable" for `incomplete`. An answer with a
material eligible claim that is not positive with its release permitted never carries the word "passed": while fidelity
review is off (D6) no answer does. `checks` holds at
most 12 entries `{claim, formal, fidelity}` for material claims, plus `checksSummary`; a faithful translation whose
evidence is unresolved or whose release is not permitted reads `without_evidence`. The page writes the labels from the
closed statuses (`vectors/chat-contract/labels.json`), never from the service's prose, shows the engine scope statement
once per answer, and no label says "verified", "true", "proven" or "Reviewed".

| Stage or decision | Raw code stored | POST answer | History shows | Unchanged retry |
|---|---|---|---|---|
| configuration incomplete (before admission) | not stored | 503 `chat_unavailable` | — | nothing was admitted |
| handshake not ready | `kit_hs_not_ready`, `kit_hs_unreachable`, `kit_hs_mismatch` | 503 `service_unavailable` (retryable) | `service_unavailable` | re-arms (nothing paid was sent) |
| subject unmapped or unavailable | `specialist_unmapped`, `specialist_unavailable` | 503 `chat_unavailable` | `chat_unavailable` | re-arms |
| specialist outcome other than `answer` (base M simulation) | `specialist_<outcome>` | 422 `review_unresolved` (cancel: the existing cancel handling) | the same | final on base P |
| `refuse_unresolved` | `kit_dl_002`, `-007`, `-008`, `-010`, `-012`, `-020` | 422 `review_unresolved` | `review_unresolved` | final on base P |
| `refuse_incomplete`, a failed checks call | `kit_dl_004`, `-011`, `-013`, `-900`, `verifier_*` | 503 `checks_incomplete` | `checks_incomplete` | final on base P |
| `refuse_integrity`, a release-gate refusal | `kit_dl_001`, `-003`, `-005`, `-006`, `-030`, `verifier_malformed`, `verifier_binding_mismatch`, `kit_gate_*` | 502 `upstream_invalid` | `upstream_invalid` | final on base P |
| `deliver` | — | 200 answer with `review: "checks:integration.v1"`, `checks`, `checksSummary` | the answer | replay |

`website/src/verify/codes.js` holds this raw-to-public map as a closed table whose keys are exactly
`errors.WORKER_RAW_CODES` (`vectors/codes/`).

## 9. The delivery rule (normative)

An answer (single, a consolidated duplicate, or a combined synthesis) is shown to a student only when every condition
holds, checked in this order; the first that fails names the refusal:

1. the verification configuration is complete (check 3);
2. the handshake is current and compatible (check 4);
3. the routed subject is mapped and its specialist available (check 5);
4. the attempt is still pending (before the specialist call, before the checks call, and in the fenced completion);
5. every contributing specialist's outcome is `answer`;
6. the verdict is well formed and bound to this `task_id`, `request_id`, `user_text_sha256` and these answer digests;
7. the receipt is not REJECTED and carries no error-level finding, and the FINAL audit passed;
8. the overseer's delivery decision allowed delivery (`delivery_decision`, or `release_decision` in combined mode);
9. decision-table rows 3 to 6 do not refuse under the named policy;
10. the Worker re-derives the same decision from the verdict's fields;
11. the text released is byte-identical to the checked deliverable (digest comparison: the release gate hashes the
    result's text and compares it with the deliverable's `answer_sha256`, whatever produced the result);
12. the ChatResult passes the website's own gate, its size is at most 64 KiB, `review` is `checks:integration.v1`, and
    `checks` agree with the verdict's claims;
13. the labels are truthful: nothing non-definitive is labelled checked, and the answer's badge says "passed" only
    when its summary is `formally_checked` (every material eligible claim positive with its release permitted); the
    scope statement is present whenever a formal status is shown; `simulated` is true unless both the specialist and the
    checks are live.

Only then does the website store the result, which is then replayed unchanged. **The rule holds in every case: an
answer whose required checks did not complete is never labelled as checked, whatever the policy.**

## 10. Bounded revision (off; decision D5)

No v1 policy allows a revision, so `revise` is never produced. If D5 allows one: a revision notice built by code
(finding codes and excerpts, never agent text), a new runtime call with its own budget, a new checks call with
`revision_of`; a second `revise` becomes `refuse_unresolved` with KIT-DL-020.

## 11. Twofold modes

- **Duplicate**: two instances of one specialist (`<slug>@a`, `<slug>@b`), the same input; the overseer's consolidation
  picks the representative; CONFLICTING and NO_DELIVERABLE_OUTPUT are `refuse_unresolved`. Only in the simulation and
  for routes the policy lists (D19).
- **Combined**: two different specialists after the router's `clarify/mixed_request` and an explicit choice by the
  student (D19); a combinator synthesis; `release_decision` on the synthesis receipt; no half answers. Not offered until
  a combinator is connected.
- **How the overseer reviews** (in depth, split, duplicated, n-fold) is the flash router's advisory plan under the
  enforced floor (section 7a); it never changes a clearance, a release or a decision, the router only gets what is
  left of the budget (at most 3 s), and the review itself runs after delivery.

## 12. Closed error codes (`integration/errors.py`)

**Start-up and handshake (`KIT-HS`)**: 001 `protocol_unsupported`, 002 `component_versions_mismatch`, 003
`z3_unavailable`, 004 `selftest_failed`, 005 `stem_unavailable`, 006 `named_policies_unavailable`, 007
`overseer_unavailable`, 008 `signing_unconfigured`, 009 `translation_provider_unconfigured`, 010
`subject_map_mismatch`, 011 `specialist_contract_unsupported`, 012 `environment_mismatch`, 013 `limits_incompatible`,
014 `transport_unconfigured`, 015 `handshake_unreachable`, 016 `timing_infeasible`. A refusing service prints one line
and exits with status 2; a refusing Worker refuses the turn.

**Request validation (`KIT-REQ`, HTTP 400)**: 001 `envelope_invalid`, 002 `mode_unsupported`, 003 `policy_unknown`,
004 `ids_invalid`, 005 `self_certification_rejected`, 006 `too_large`, 007 `budget_out_of_range`, 010
`specialist_schema_unsupported`, 011 `specialist_contract_unsupported`, 012 `specialist_not_an_answer`, 013
`specialist_gate_not_passed`, 014 `answer_digest_mismatch`, 015 `subject_unmapped`.

**Delivery reasons (`KIT-DL`)**: 001 `receipt_rejected`, 002 `receipt_error_findings`, 003 `clearance_failed`, 004
`clearance_pending`, 005 `final_audit_not_passed`, 006 `delivery_refused`, 007 `consolidation_conflicting`, 008
`no_deliverable_output`, 010 `blocking_formal_result`, 011 `checks_incomplete`, 012 `ambiguous_material_claim`, 013
`budget_spent`, 020 `revision_exhausted`, 030 `worker_binding_mismatch`, 900 `internal_error`.

**Overseer port (`KIT-OP`)** 001 to 012, **combinator port (`KIT-CB`)** 001 to 006, **flash-router port (`KIT-RT`)**
001 to 016 and 020: as in sections 6, 7 and 7a.

**Worker raw codes** (stored for operators; `^[a-z0-9_]{1,64}$`; `errors.WORKER_RAW_CODES` and `codes.js`): handshake
`kit_hs_*`; subject `specialist_unmapped`, `specialist_unavailable`; specialist outcomes `specialist_<outcome>` (runtime
v0.1.0 and v0.2.0 outcome sets); the checks call `verifier_*` (busy, cancelled, timeout, network, redirect, auth,
rate_limited, capacity, rejected, error, malformed, binding_mismatch); decisions `kit_dl_*`; the release gate
`kit_gate_*` (binding, decision, review, checks, raw_body, size).

## 13. Compatibility and change rules

`integration/COMPATIBILITY.json` pins the protocol, the accepted component versions (IR 1.0, engine 0.4.0, policy
2026.10-v4, translator 0.4.0, contract 0.4) and the `z3-solver` range, the specialist pairs, the routing contract, the
subject-map digest, the named and verdict policies, the STEM branches, the overseer's replay mode, the router's
non-required status and floor, the limits, the timing figures per website base, the website bases with tested patch
sets, and the repositories by role (`repositories`): `translator` the organization's translator repository, which
receives the verified updates; `translator_development` the development repository, which carries the kit, the
`subproject/*` branches and the kit tag; `translator_mirror` the former path of `translator`, kept so that a remote
still using it is recognized; `website`; `agents` the retrained agents repository (the specialist runtime the website
is to deploy, its exporter, the knowledge bases, the routing); `agents_harness` the training and simulation harness.
`kit_tag_repository` names the role whose repository carries the kit tag, and `agents_pins` the commits of the agents
repositories the kit was tested on (the runtime with its contract and src tree, the exporter, the knowledge bases with
the History bundle's digest, the routing, the harness); each pin's `repository` is a key of `repositories`. No service
or Worker code reads the repositories, `kit_tag_repository` or `agents_pins`: the readiness scripts and the playbook do.
It records the build identity without requiring it to match. One generated copy per side (`integration/compat.py`,
`website/src/verify/compat.js`, `subject-map.js`, the schemas) is drift-tested against it
(`integration/tools/generate.py --check`). Changing a status's meaning or removing a field needs a new major version
and the receiving owner's agreement. Adding these endpoints raises the translator's integration contract to
0.4; the engine and policy versions do not change.

## 14. Acceptance (tests, vectors, simulation, rollback rehearsal)

**14.1 Translator** (`tests/integration/`): every port's round trip and its refusal of out-of-contract input; one
handshake refusal per `KIT-HS` code; the bootstrap with Z3 hidden (exactly `KIT-HS-003 z3_unavailable`, status 2, no
traceback; also through the `epinoic-logic serve` console script); lazy CLI imports; the self-test and a tampered
digest; the TurnChecker per mode (single clean, an error finding, REJECTED; duplicate identical, chosen, conflicting;
the budget spent before and half-way; a STEM report cut by its budget; a provider failure; every overseer refusal; an
out-of-contract overseer message; an unexpected exception); the decision-table vectors and the property test; prefetch
non-interference; fixture-verifier parity with `run_arena`; service routes behind the existing gates; the evidence tap
refused outside the sim profile; the review routing with the router absent, at the floor and below it; the router in its
own process (no `EPINOIC_` variable, no patch of the floor, every way of failing refused with 016, a time limit, and on
Linux a router under the service's own unprivileged user cannot read the service's start environment; the hosted profile
attaches none where that cannot hold); a failing review that changes no decision; the binding checks on a truncated
claim list; the flash-router sub-project's own suite and its adoption on every vector; manifest freshness. The full
suite passes with no test weakened or deleted.

**14.2 Website** (offline: a fake `fetchImpl` or the loopback service, `node:sqlite` D1): the kit's adapter tests
(`website/tests/`), and once a patch set is applied, every existing test unchanged plus the contract, codes, readiness,
gate, flow, handler, pins and disclosure tests of `website/PATCH-PLAN.md`.

**14.3 Agents**: every suite reports `fail 0`; counts recorded, never pinned; the new port tests and `check:portable`.

**14.4 Cross-repository vectors** (`integration/vectors/`): canonical JSON and digests byte for byte; specialist port
v1 and v2; handshake; decision table; verdict binding (W-T1 to W-T8); chat-contract labels; codes; router port. The
translator and the Worker's adapter both pass them (`tests/integration/test_vectors.py`).

**14.5 Simulation gates** (`integration/sim/`): G-EQ-ARENA, G-EQ-CONTAINED, G-FAULT, G-INV, G-HON, G-DEL, G-TAMPER,
G-OVS, each PASS, FAIL or NOT RUN; **a gate without material is NOT RUN, never PASS**; `run_sim.py` exits 0 only when
no gate FAILs and all eight PASS (`integration/sim/README.md`).

**14.6 Dry run of a fresh session** on scratch clones: the playbook reaches step 15, chooses the kit by its tag, finds
G0 in force, makes no website branch, the simulation exits 0, and a transcript audit finds no push, deploy, secret,
remote D1 command, provider host or weakened test.

**14.7 Rollback rehearsal** (`integration/rollback/ROLLBACK.md`; playbook step 11a): W1 alone replays rows written by
W3; removing W3 leaves every row valid; an incompatible service gives `service_unavailable` or `chat_unavailable`,
never an unchecked answer; on base P removing patch set P leaves the pilot unchanged.

---

## Appendix A. Statements carried verbatim

- **Engine scope statement**: "This result concerns only the formal encoding it is bound to, under the encoded
  premises and the stated solver configuration. It does not establish that the premises are factually true, that the
  natural-language claim was translated faithfully, or that any interpretive judgement is correct. Grounding and
  semantic-fidelity information is reported separately and is advisory."
- **Audit scope sentence** (overseer TR6): "This audit covers only the transfers journaled since the auditor was
  attached to the channel. It shows whether the recorded transfers, receipts and signed results agree with each other
  and with this repository's rules. It does not show that any claim is true or any reading correct."
- **Specialist gate disclaimer** (runtime): "Deterministic format and policy heuristics. Not factual, academic or
  formal verification."
