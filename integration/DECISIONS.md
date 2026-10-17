# Decisions for the founder and the owners

**Every decision below is decided** (17 October 2026, under Daniel's delegation of that day: "determine yourself on all
the rest of the decisions"); each row points to its entry in the record that follows the table ("Integration kit:
decisions of record"). Owners: the website belongs to Bruno; the translator and the agents repositories belong to
Daniel; "founder" is the founder of Epinoic AI. Where the kit named Bruno or the founder as the decider, the record is
the programme's decision of record, which Bruno may override for his own repository.

**Deciding changes no behaviour by itself.** The kit still implements the fail-closed default each row names, and
every default fails closed. Where the decided behaviour differs from that default, "Kit changes the decisions require"
(after the table) lists the files to change; those changes are the programme's, in a later step, and until they are
made the default stays in force. No owner action of the record has been performed (the record lists them, in order,
under "Owner actions, in M2 order"), and the website integration stays deferred (gate G0).

| # | Decision | Who decides | Kit default (in force until the kit change below is made) | Status |
|---|---|---|---|---|
| D1 | Record "Z3 is required" in the website repository: lift the 12 October deferral, invariant 25 and the two notices (W0) | Bruno | Website work stays a patch file and a disposable export; gate G0 is evaluated on `origin/main` | decided; W0 pending (Bruno) ([record](#d1-record-z3-is-required-in-the-website-repository)) |
| D2 | When checks cannot complete for a material eligible claim: refuse (503 `checks_incomplete`), or release qualified, labelled "check unavailable" | founder, with Bruno | Refuse (`verified-v1`) | decided ([record](#d2-when-checks-cannot-complete-for-a-material-eligible-claim)) |
| D3 | Do COUNTEREXAMPLE, INCONSISTENT_PREMISES and UNSATISFIABLE on a material claim block the answer, including COUNTEREXAMPLE with only the advisory W110/W111 | founder | Block | decided ([record](#d3-negative-definitive-results-on-a-material-claim)) |
| D4 | AMBIGUOUS_TRANSLATION on a material claim: qualify, block, or a clarification written by the website | founder, with Bruno | Qualify, labelled ("Not formally checked: more than one reading") | decided ([record](#d4-ambiguous_translation-on-a-material-claim)) |
| D5 | One bounded revision, or none | founder, with Bruno (budget) | None: `revise` is never produced | decided ([record](#d5-bounded-revision)) |
| D6 | Wire a cheapest-tier fidelity reviewer (without one, nothing can be labelled "formally checked"; one more call per translated claim) | founder | Not wired: `formal_only` at best | decided ([record](#d6-a-cheapest-tier-fidelity-reviewer)) |
| D7 | Hosting: a container behind a service binding or external HTTPS; who operates it; per-environment deployments and tokens; capacity | founder, Daniel, Bruno | No deployment; `deploy/container/` is PROPOSED only | decided ([record](#d7-hosting)) |
| D8 | Who extracts claims | founder | The translator's branch parsers, in the service; specialists keep `claims: null`; the website never extracts | decided ([record](#d8-who-extracts-claims)) |
| D9 / D10 | Mapping subjects to slugs; which specialist `english` means; STEM subjects on the website | Bruno, with Daniel | History only on the website; `english` is mapped only in the `sim` environment (to a synthetic `english-a-literature` specialist); STEM checked by the service and the agents driver only | decided ([record](#d9--d10-subjects-slugs-and-stem-on-the-website)) |
| D11 | Mapping ids: `task_id` = turnId, `request_id` = attemptId | Bruno | As stated | decided ([record](#d11-identifier-mapping)) |
| D12 | Signing the verdict: HMAC plus an authenticated channel plus the Worker's binding checks, or Ed25519 (a new dependency) | founder | HMAC; the Worker checks bindings and re-derives, and never claims to verify the HMAC | decided ([record](#d12-signing-the-verdict)) |
| D13 | Display: `checks` and `checksSummary`, the label copy, the disclosure copy, the `simulated` semantics, the copy of the two new codes | Bruno | PROTOCOL.md section 8 proposals; simulated unless both parts are live | decided ([record](#d13-display-copy-and-the-simulated-semantics)) |
| D14 | Budgets and caps for specialist, checks and provider calls, and who approves them; the form of W5 | Bruno (website task 04), founder | No caps approved, so no live calls | decided ([record](#d14-budgets-and-caps)) |
| D15 | Data terms and retention for the verification host and its provider; whether a subset of the recorded rounds may ship in the kit corpus (`corpus/licensed/`) | founder, Daniel | Nothing retained; synthetic corpus only | decided ([record](#d15-data-terms-retention-and-the-kit-corpus)) |
| D16 | Delivery: synchronous within the base's deadline, or asynchronous | Bruno, founder | Synchronous | decided ([record](#d16-synchronous-or-asynchronous-delivery)) |
| D17 | Delivery-rule parameters seen in a brief but in no repository ("a four-minute budget", "overseer selection above 90%", "never labelled checked") | founder | A budget bounded by the base's deadline; no selection threshold; "an answer whose required checks did not complete is never labelled checked" always on | decided ([record](#d17-the-delivery-rule-parameters)) |
| D18 | The overseer: embedded for v1; when a sidecar may replace it; agents asynchronous and advisory; removing the simulation adjudicator's power to clear formal errors | founder, Daniel | Embedded, asynchronous, power removed | decided ([record](#d18-the-overseer-embedded-sidecar-agents-adjudicator)) |
| D19 | Twofold modes: which routes use duplicate (cost x2); the contract and router path of the combined mode | founder, Bruno | Single only on the website; duplicate and combined only in the simulation; combined not offered until a combinator is connected | decided ([record](#d19-twofold-modes)) |
| D20 | Repositories: the T1 base contents; the canonical translator remote that carries the tag and the pointer; whether the mirror gets the pointer; the canonical agents repository; the visibility of the translator repository and whether the website patch files may be published in it; the licence for kit material that goes into a public repository | Daniel, with Bruno for the website files | Tag and pointer on `origin` (proposed); **no `W*.patch` file published while the translator repository is public** (only `apply.mjs`, the kit-authored code blocks, `ANCHORS.md` and `RESULT.sha256`); no kit material copied into the public agents repository | decided ([record](#d20-repositories-and-visibility)) |
| D21 | `verified` as the only path to real answers on hosted environments (no specialist backend without checks) | founder | Pinned | decided; pins pending in patch set P ([record](#d21-verified-as-the-only-hosted-path-to-real-answers)) |
| D22 | What happens to overseer-agent findings after delivery (a human review queue, a notification) | founder | Recorded only | decided ([record](#d22-overseer-agent-findings-after-delivery)) |
| D23 | Approving model identifiers for the specialist tier and the cheapest tier (translation, combinator, overseer agents, any model the flash router's cost data refers to) | Bruno (website task 03), founder | None approved: model ids stay a placeholder of the owner's configuration (`EPINOIC_ANTHROPIC_MODEL`, `EPINOIC_OPENAI_MODEL`); no plan or message ever names one | decided ([record](#d23-model-identifiers)) |
| D24 | Conversation context for follow-ups (`priorTurns`), and where it is stored under KEEP and hard delete | Bruno | Website 01 decides; the kit is unaffected | decided ([record](#d24-conversation-context-for-follow-ups)) |
| D25 | Timing of a verified turn on base P: keep 25 s and shorten the provider timeout; a longer synchronous deadline; asynchronous delivery; or only deterministic checks on the critical path | Bruno, with the founder | None chosen: on base P the verified backend refuses with `KIT-HS-016` | decided ([record](#d25-timing-of-a-verified-turn-on-base-p)) |
| D26 | Retry semantics after the specialist call: refusals final, or re-armable at the cost of a second generation; the codes `review_unresolved` and `checks_incomplete` and their copy | Bruno | Final | decided ([record](#d26-retry-semantics-after-the-specialist-call)) |
| D27 | The review value `checks:integration.v1` and its page badge, which follows the answer's `checksSummary` | Bruno | The conservative copy (`chat-contract.js checksBadge`, vectors `chat-contract/labels.json` `badges` and `badge_cases`): "Automatic checks passed" (success tone) only for `formally_checked`, where every material eligible claim has a positive result whose release is permitted (unreachable while D6 leaves fidelity review unwired); "Partly checked" for `partly_checked` and "Partly checked (encoding only)" for `formal_only`, with no success tone, because either may hold material claims that are not formally checked or positive results of the encoding only; "Not formally checked" for `not_formally_checkable` and any unknown summary; "Some checks unavailable" for `incomplete` (reachable under `verified-v1-qualify` only). No answer with a material eligible claim that is not positive and permitted says "passed" | decided ([record](#d27-the-review-value-and-its-badge)) |
| D28 | The flash router as a separate, independent sub-agent: the sub-project `flash-router/` (package `epinoic_flash_router`, first release 0.1.0 in this kit), who maintains and releases it, its release cadence apart from the Z3 infrastructure, and whether hosted environments attach it | founder, Daniel | Not attached: the service attaches the router only when `EPINOIC_FLASH_ROUTER` names it; unset or `none` (the default) runs the floor plan for every review; the handshake reports the router absent and never requires it. When attached it runs in its own process with no `EPINOIC_` variable, at most `min(3 s, budget left)` per plan. That process is a fault boundary, not a sandbox: it runs as the service's user; on Linux the non-dumpable service keeps its keys out of a router without root or `CAP_SYS_PTRACE`, and the hosted profile attaches a router only there (`KIT-RT-016` otherwise); so a router is code trusted with the service's user, and whether hosted environments run it under a user or sandbox of its own is part of this decision. Also part of this decision: the repository form (today a sub-project directory of the translator repository, released by its own version and identity, not a separate repository or submodule with its own tag; `git subtree split --prefix flash-router` makes one if the owners want it) and whether the translator's suite keeps running the router's own suite | decided ([record](#d28-the-flash-router-as-a-separate-sub-agent)) |
| D29 | The minimum-oversight floor (`minimum-oversight-floor/1`): its agreement signals, the 2 independent reviews they call for, N_FOLD for a combined answer, the 65,536-byte temporary context; whether named argument diagnostics and unverified dependencies become floor signals (`minimum-oversight-floor/2`) once the diagnostics are connected | founder | As in `router_port.FLOOR_RULES`: floor/1 reads neither diagnostics nor unverified dependencies (a router may escalate on them, the flash router's first release does); the floor can only be raised by a new floor version with its own digest, never lowered by a router | decided ([record](#d29-the-minimum-oversight-floor)) |
| D30 | The overseer-agent profiles a plan may choose (`standard`, `fast`) and whether `fast` is offered at all | founder, Daniel | Only the profiles the overseer's hello lists; the floor runs `standard`; the profile is not part of the floor | decided ([record](#d30-overseer-agent-profiles)) |
| D31 | The task type the website sends with a check (the website carries none today) | Bruno | `short_answer` | decided ([record](#d31-task-type)) |
| D32 | Per-call timeout of a live cheapest-tier translation provider | founder | 20 s (`runtime.PROVIDER_TIMEOUT_S`), proposed; no live call is made until D14 and D23 | decided ([record](#d32-live-provider-timeout)) |
| D33 | The combinator as a separate agent: the sub-project `combinator/` (package `epinoic_combinator`, first release 0.1.0 with instruction pack `combinator-instructions` 1.0; 0.1.1 with pack 1.1, which states the repeated-citation rule and the verification-label rule; 0.1.2 with the same pack 1.1, whose contract gate holds a message passed already parsed to the protocol's JSON rules first, as the port does; now 0.1.3 with pack 1.2, which states the note rule (a source claim roled `other` is never cited), the engine-verdict and status-mark labels, the frequency, bound and minority qualifiers, the credit rules, that a conflict is listed only when the claims really disagree and that a reason is written in words, under a contract whose combinator texts are words (`combinator_port.TEXT_PATTERN`: never blank, no control character but a tab or a line break, no bidirectional control)), who maintains and releases it apart from the Z3 infrastructure, its repository form (today a sub-project directory of the translator repository; `git subtree split --prefix combinator` makes one, steps in `combinator/README.md`), whether the translator's suite keeps running its suite, how the service runs it (its own process with a provider credential, or a sidecar) and which provider and model it calls | founder, Daniel | Not connected: `EPINOIC_COMBINATOR` is `none`, the capabilities omit `combined` and the checks port refuses it (`KIT-REQ-002`); no live provider exists in the sub-project and no model is named (D23); the translator never imports it, validates everything it returns as untrusted data and relays a checked synthesis through its hub, which decides it | decided ([record](#d33-the-combinator-as-a-separate-agent)) |

## Kit changes the decisions require

Each decision whose decided behaviour differs from the kit's current default, with the files to change. None of these
changes is made yet; the kit's behaviour is the default in the table until each one is.

- **D1** (W0 text): `website/W0/w0.json` (the drafter `website/W0/draft-w0.mjs`, its `TESTED.json` re-run): the W0 draft
  also names this record ("decisions D1 to D27 decided 17 October 2026"), states the D25 deadline and the D21 rule,
  and adds the notes the website's `AGENTS.md` asks for to `docs/current-state.md` and `docs/architecture.md`.
- **D2** (INVALID_FORMALIZATION is incomplete; policies by environment): `src/epinoic_logic/integration/delivery.py`
  and `website/src/verify/decision-table.js` (row 5 adds INVALID_FORMALIZATION); `integration/COMPATIBILITY.json`
  (`verdict_policies_by_env`); `checks_port.py` (a policy outside the environment's list is `KIT-REQ-003`),
  `capabilities.py` (`policies` lists the allowed ones), `website/src/verify/verification.js` (qualify offered on a
  hosted environment is `kit_hs_mismatch`); new decision-table vectors; `tools/generate.py`, `tools/vectors.py` and
  the MANIFEST regenerated; `PROTOCOL.md` section 8.
- **D4** (AMBIGUOUS_TRANSLATION on a material claim withholds on hosted environments): `delivery.py` and
  `decision-table.js` row 6 (`refuse_unresolved`, `KIT-DL-012`, under `verified-v1`; qualify continues) with their
  tests; the decision-table vectors (the labelled-ambiguity vector moves to the qualify policy; a new refusal vector);
  `PROTOCOL.md` section 8.
- **D6** (a cheapest-tier fidelity reviewer, `off` by default): `integration/settings.py` (`EPINOIC_FIDELITY_REVIEW`,
  `EPINOIC_FIDELITY_REVIEWS_PER_DAY`), `preflight.py` and `errors.py` (`KIT-HS-017 fidelity_review_unmeasured` for `on`
  or a fixture reviewer when hosted), `protocol.py` (`translation.reviewer`: `none`, `fixture`, `shadow`, `live`), the
  schemas and handshake vectors, `turn.py` (the reviewer in the task-aware verifier; shadow reviews only after the
  verdict is signed), the new tests the record lists; `PROTOCOL.md` sections 5.3 and 12.
- **D7** (M2 hosting values): `deploy/container/README.md` (the values, the hosting ceiling, `TRANSLATOR_MODE=http`
  for staging); `readiness/check.py --live` (the host requirements as owner rows, names only).
- **D13** (display copy, `simulated`): the W4 disclosure block (its M2 variant from `outcome.kit.simulated === false`;
  the M1 copy and its three leads), `website/src/verify/with-verification.js` (`kit.specialistLive`,
  `kit.checksLive`), the W1 review-states block (`checksBadge` drops the success tone with the " (simulated)" suffix),
  `vectors/chat-contract/labels.json` and `website/tests-website/verify-disclosure.test.js` (the new cases); website
  `RESULT.sha256` and `TESTED.json` re-run.
- **D14** (caps and keys, every default 0): `settings.py` (the five caps and `EPINOIC_ANTHROPIC_API_KEY`,
  `EPINOIC_ASYNC_ANTHROPIC_API_KEY`, names only), `translate/providers/anthropic_provider.py` (a key passed explicitly,
  never the SDK default), `turn.py` (a reached cap or a spending-limit error is `provider_unavailable`, no retry; the
  asynchronous provider from its own key), `preflight.py` and `errors.py` (`KIT-HS-018 live_calls_not_enabled`;
  `KIT-HS-009` for the SDK default variable on a hosted environment), `readiness/check.py --live` (owner rows), the
  new tests the record lists; patch set P (the `checks` reservation kind).
- **D15** (the licensed corpus only from a private repository): `tools/build_corpus.py --licensed` (refuses while
  `COMPATIBILITY.json` `repositories.translator_visibility` is not `private`), that new field (default `public`),
  `sim/corpus/DATA-TERMS.md` and `deploy/container/README.md` (the terms).
- **D16** (synchronous delivery declared): `protocol.py` (a required capabilities field `delivery`, v1 value
  `["sync"]`), `schemas/capabilities.v1.schema.json`, every handshake vector (and a new one refusing its absence),
  `compat.py`, `compat.js`, `verification.js` (validation), the MANIFEST; `PROTOCOL.md` (a "1.1 (planned)" note).
- **D17** (the M3 fallback, reserved): `protocol.py`, `website/src/verify/codes.js` and the vectors reserve
  `verified-v1-fallback`, `overseer_selected` and `selected:integration.v1`; `PROTOCOL.md` section 9 states the
  fallback as a separate path that is never "checked".
- **D20** (sub-project branches, visibility): `integration/COMPATIBILITY.json` (`repositories.translator_visibility`,
  `repositories.subproject_branches`); `integration/README.md` and `combinator/README.md` (the `subproject/<name>`
  branches and how to split one; `flash-router/README.md` already says so).
- **D21** (`verified` the only hosted path): patch set P (not built) adds the three release tests and the replaced
  var-block guards the record lists.
- **D22** (findings after delivery): the service's metadata-only `review_result` log event and
  `python -m epinoic_logic.integration summary --week` (counts only).
- **D23** (models by tier): `readiness/check.py --live` (whether a model is configured, names only; the assignment
  version `2026-10-13.1`).
- **D25** (base P deadline 100 s): `integration/COMPATIBILITY.json` `timing.bases.P` (`deadline_ms` 100,000;
  `specialist_ceiling_ms` 20,000; `checks_tail_ms` 5,000), `vectors/handshake/base-p-timing.json` (feasible) and a new
  vector keeping 25 s at `KIT-HS-016`, `compat.py`, `compat.js`; `website/PATCH-PLAN.md` (the pilot constant).
- **D27** (supporting claims in the summary): the verdict's `counts` gain `supporting_eligible` and
  `supporting_permitted`; `delivery.summarize`, `decision-table.js` and `release-gate.js` give `formally_checked` only
  when both the material and the supporting eligible claims are all permitted; the property test, the decision and
  badge vectors the record lists, `selected:integration.v1` reserved; `PROTOCOL.md` sections 8 and 9; the schemas,
  `compat.py`, `compat.js` and the MANIFEST regenerated.
- **D29** (`minimum-oversight-floor/2`): `router_port.FLOOR_RULES` version 2 (an error-level named diagnostic and an
  unverified dependency call for 2 reviews), its digest and vectors, when the argument diagnostics are connected
  (`routing_features.OutputRecord.diagnostics`).
- **D30** (the `standard` profile only): the rebuilt overseer's port adapter's hello lists `["standard"]` (connected
  with the overseer).
- **D33** (the combinator's process when connected, M3): the launcher that gives its process only the cheapest-tier
  provider credential and the model configuration.

Documentation only, or nothing: D3 (`PROTOCOL.md` section 8 says W110/W111 do not soften row 4), D5 (protocol 1.1),
D8, D9/D10, D11, D12 (the rotation procedure in `deploy/container/README.md` and `rollback/ROLLBACK.md`), D18 (the
staging value in `deploy/container/README.md`; A5 is built in `agents/`), D19, D24 (a test that no prior-turn text is
sent), D26, D28 (the sub-project branch, in `flash-router/README.md`), D31, D32.

## Withdrawn kit tags

None. A published tag is never moved or deleted; a bad kit is withdrawn by naming the previous or the next tag in
`INTEGRATION_KIT.md` and by listing the bad tag here.

---

# Integration kit: decisions of record, D1 to D27

**Decided 17 October 2026** under Daniel's delegation of that day: "determine yourself on all the rest of the
decisions". Every open decision D1 to D27 of the integration kit is decided below with concrete values, under the
numbering that `integration/DECISIONS.md` uses.

How to read this record:
- **A decision is documentation.** It never deploys, changes DNS, enables a paid call, changes production access, sets
  a secret, runs `wrangler d1` against a remote database or a production migration, or changes the website repository.
  Each such action is listed under "Who acts, when" with its owner, and happens only at the programme's last task
  (the website integration), with that owner's own go. The full list, in M2 order, closes this record.
- **Authority.** Where the kit design named Bruno or the founder as the decider, the entry below is the programme's
  decision of record, which the kit implements. Each such entry says in one line that Bruno may override it for his own
  repository.
- **Limits that hold whatever is decided.** The IR is data and is never executed. Consistency comes before entailment.
  A non-success status is never shown as success. Results prove properties of the logic encoding only, and the scope
  statement is kept verbatim. Agent self-reports are advisory; only signed engine results are trusted. No test is
  weakened. No deployment or live integration is claimed without evidence. Required review must pass before an answer is
  released, and a mock `passed` label is not a review. Z3 is required on the delivery path and must integrate
  seamlessly. No optimisation work now. No new GitHub repository. No spending limit is ever raised.
- **Models** are named only by tier ("the cheapest tier", "the specialist tier") and by their entry in the agents
  repository's `agents/model-assignment.json`. The concrete identifier is set by its owner as service configuration.
- **References.** Section numbers are those of `integration/PROTOCOL.md`. A fact from outside this repository is
  stated inline with where it was inspected; "inspected 17 October" means read on that day, not re-checked since.
  "Base M" is the website's `main` without the History pilot stack. "Base P" is `main` after the pilot stack (website
  pull requests #21 to #24). M1 is the local simulation. M2 is the staging pilot. M3 is asynchronous delivery, which is
  decided here (D16) and built after M2.

---

## Summary

| # | Decision | Who acts |
|---|---|---|
| D1 | Z3 is required on the website's delivery path. The 12 October deferral is superseded, and W0 records this in the website repository | Bruno merges W0 (last task) |
| D2 | On every hosted environment, an incomplete check on a material eligible claim withholds the answer (`verified-v1`). INVALID_FORMALIZATION counts as incomplete. `verified-v1-qualify` is allowed only in development and `sim` | nobody: the kit implements it |
| D3 | COUNTEREXAMPLE, INCONSISTENT_PREMISES or UNSATISFIABLE on a material claim blocks the answer, including COUNTEREXAMPLE with only the advisory W110/W111. `verified-v1` is fixed at the first kit tag | nobody: the kit implements it |
| D4 | AMBIGUOUS_TRANSLATION on a material claim withholds the answer on hosted environments (422 `review_unresolved`, KIT-DL-012). It is qualified, with its label, only in development and `sim` | nobody: the kit implements it |
| D5 | No revision in synchronous delivery (M2). One bounded revision in asynchronous delivery (M3), inside the four-minute formal budget | nobody now; Bruno approves the revision budget at M3 |
| D6 | Wire the translator's existing semantic-fidelity reviewer on the cheapest tier, given only what `build_review_request` assembles from the turn (never the specialist's knowledge bundle). Shadow mode on staging runs after the verdict is signed, on the asynchronous queue, under its own cap and key, so it cannot change a verdict. `on` only after a 95% Wilson lower bound of at least 0.98 and a new kit tag | the kit implements it; Daniel switches it on after M2 |
| D7 | M2 hosting: one external HTTPS container per environment, operated by Daniel: 1 instance, 4 slots, 60 calls per minute, at least 3 GiB, under a hosting ceiling of USD 30 a month. The Container binding comes later, with Bruno | Daniel hosts; Bruno sets the Worker token (last task) |
| D8 | Claims are extracted by the translator's branch parsers in the service. Specialists keep `claims: null`, and the website never extracts | nobody: the kit implements it |
| D9 / D10 | Only History on staging. `english` maps to `english-a-literature` in `sim` only; development, staging and production answer `specialist_unmapped` (the subject map as built). No website STEM route before M3; the service checks STEM | nobody: the kit implements it; Bruno schedules W7 |
| D11 | `task_id` = turnId, `request_id` = attemptId | nobody: the kit implements it |
| D12 | HMAC-SHA256 under three distinct keys, rotated every 90 days. Ed25519 is deferred to protocol 1.1 | Daniel generates the keys (last task) |
| D13 | The kit's label and error copy is adopted, with disclosure copy that is true of every released answer: answers are shown only after automatic checks allow them, the main claims' encodings are checked where they can be expressed in logic, supporting statements may not be, and each badge says what was checked. An answer is `simulated` unless both the specialist and the checks are live; a simulated badge never has the success tone | Bruno merges it with patch set P (last task) |
| D14 | Conservative ceilings, every default 0 (fail closed). Staging website: 100 verified turns a day, 20 per principal. Service delivery path: 2,000 provider calls, 20,000,000 input and 2,000,000 output tokens a day, under a USD 20 a month hard limit on its own key (`EPINOIC_ANTHROPIC_API_KEY`). Asynchronous work (overseer agents, shadow fidelity reviews): 25 and 200 reviews a day, under a USD 5 a month hard limit on a separate key (`EPINOIC_ASYNC_ANTHROPIC_API_KEY`); without its cap or key it is disabled at start-up and deliveries run unchanged. A hard limit reached mid-month withholds every staging verified turn until the provider's monthly reset. Specialist key: USD 25 a month. Production: zero. W5 is a `checks` reservation kind | Bruno (website budget, specialist key), Daniel (service keys) (last task) |
| D15 | The service keeps no request or response bodies, and its metadata logs are kept at most 30 days. The provider must not train on inputs and must keep them at most 30 days. Only Access-protected testers use staging. The licensed corpus ships only once the repository is private | Daniel (provider terms), Bruno (website notice) (last task) |
| D16 | Synchronous delivery for M2. Asynchronous delivery (protocol 1.1) is the M3 target that carries the four-minute budget | nobody now; Bruno designs the website side at M3 |
| D17 | Daniel's rule is confirmed. The four-minute formal budget applies in asynchronous delivery. An answer whose formal checks did not complete may be shown only when the overseer selects it with accuracy above 0.90, on two validated reviews; it is never labelled checked, and otherwise it is withheld. The fallback is specified, not built, and stays off on hosted environments until its 95% Wilson lower bound is at least 0.90; its 120 s overseer deadline and the 420 s job ceiling are provisional until standard-profile latency is measured. Synchronous delivery withholds within the checks budget (at most 65 s) | the kit implements it at M3; Daniel enables the fallback after measurement |
| D18 | The overseer is embedded in v1. A sidecar replaces it only after passing the conformance suite. Overseer agents run asynchronously and are advisory. The simulation adjudicator's power to clear formal errors is removed | the kit implements it; Daniel applies A5 in the agents repository (last task) |
| D19 | The website uses single mode only. Duplicate mode never runs on the website. Combined mode only from M3, with the student's consent, W8, a connected combinator and the N_FOLD floor | nobody now |
| D20 | No new repositories. Sub-projects live on `subproject/<name>` branches of the development repository. The tag and the pointer go on `origin`, and the mirror gets no pointer. The development repository becomes private. Agents changes go on a branch of the agents repository | Daniel (visibility, tag) (last task) |
| D21 | `verified` is the only hosted path to real specialist answers. Decided; the pins are pending in patch set P, which is not built yet | Bruno merges the pins with patch set P (last task) |
| D22 | Overseer-agent findings after delivery are recorded as metadata with a weekly summary. Nothing retracts a delivered answer automatically. No per-item human queue in v1 | nobody: the kit implements it; Daniel reads the summary |
| D23 | Approve the `policy.defaultPrimary` entry (cheapest tier) of `model-assignment.json` version 2026-10-13.1 for every deployed role. The comparison entry is not approved. There is no runtime fallback | Daniel sets the service's model id; Bruno sets the specialist's model id (last task) |
| D24 | The website decides prior-turn context. The kit never sends prior turns to the service | Bruno (website 01) |
| D25 | Base P staging deadline: 100 s from receipt. Specialist ≤ 20 s; service checks budget `min(65 s, deadlineAt − now − 5 s − 2 s)`, refused below 3 s; Worker checks timer = budget + 5 s; completion reserve 2 s | Bruno sets the pilot deadline (last task) |
| D26 | Refusals after the specialist call are final. `review_unresolved` (422) and `checks_incomplete` (503) are not retryable, with the kit's copy | Bruno merges them with patch set P (last task) |
| D27 | The review value is `checks:integration.v1`, and the badge follows `checksSummary` (conservative copy). `formally_checked` needs every eligible claim, material or supporting, positive with its release permitted; an eligible supporting claim that is not makes the summary at most `partly_checked`. An M3 fallback answer gets `selected:integration.v1` | Bruno merges them with patch set P (last task) |

---

## How the coupled decisions fit

### A. What blocks, what qualifies, and what may be labelled checked (D2, D3, D4, D6, D21)

One rule covers the website and the service: **on a hosted environment an answer is released only when the
deterministic review passed and every material eligible claim reached a definitive result that is not negative.**
- **The deterministic review** is the receipt, the clearances, the FINAL audit and the overseer's `delivery_decision` or
  `release_decision`. It always runs, Z3 included. A failure there is `refuse_integrity` (502) or `refuse_incomplete`
  (503).
- **Blocks (withheld, final):**
  - a negative definitive result on a material claim (D3, row 4, `refuse_unresolved`, 422);
  - AMBIGUOUS_TRANSLATION on a material claim (D4, row 6, `refuse_unresolved`, 422);
  - UNKNOWN, TIMEOUT, INTERNAL_ERROR, INVALID_FORMALIZATION or NOT_ATTEMPTED on a material eligible claim (D2, row 5, `refuse_incomplete`, 503).
- **Qualified (released with "not formally checked" labels):** a material claim that is NOT_ELIGIBLE or UNSUPPORTED.
  These claims lie outside what the encoding can express, so the formal path has finished with them. Without this, no
  History answer could ever be released, since most of its claims are interpretive.
- **Labelled checked:** only a positive definitive result with `release_permitted`, which needs a faithful,
  evidence-bound fidelity review (D6). The badge says "Automatic checks passed" only when the summary is
  `formally_checked`, which needs every eligible claim of the answer, material or supporting, to be positive with its
  release permitted (D27). A supporting claim never blocks the answer (rows 4 and 5 count material claims only), but an
  eligible supporting claim that is not positive and permitted keeps the summary at `partly_checked` or below, so the
  word "passed" never sits on an answer one of whose own checks did not pass. While D6 is in shadow mode, no hosted
  answer can reach that badge; the best it can say is "Partly checked (encoding only)". That is the honest
  consequence: the page copy (D13) never says that checks passed, and each answer's badge says what was checked.
- **Only path:** on hosted environments, `verified` is the only backend that serves real specialist answers (D21). A
  configuration with no checks is refused, not served.
- **Development and `sim`** may also use `verified-v1-qualify`, which releases incomplete or ambiguous answers with
  "Check unavailable" or "more than one reading" labels. This is for tests and for measuring refusal rates only. The
  service refuses that policy on staging and production (KIT-REQ-003).

### B. Delivery and timing (D16, D17, D25, with D5)

Daniel's delivery rule: a four-minute formal budget; if it does not complete, an overseer-selected fallback above 90%
accuracy; otherwise the answer is withheld. The website's clocks, as inspected on 17 October, decide what is
buildable:
- the page gives up waiting after 190 s (`public/chat-logic.js`);
- `waitUntil` keeps work alive for at most 30 s after a response or a client disconnect (Cloudflare's documented limit;
  re-check before M3);
- the History pilot's draft deadline is 25 s from receipt, chosen because `waitUntil` lasts at most 30 s;
- the timing invariant `specialist_ceiling_ms + checks_min_ms + checks_tail_ms + completion_reserve_ms ≤ deadline_ms`,
  which the Worker and the service check before admission and in the handshake (`KIT-HS-016 timing_infeasible`).
  `checks_tail_ms` is the settle margin.

A 240 s budget therefore cannot be synchronous. Overseer agents are unmeasured live, and even their uncommitted fast
profile only targets 30 to 90 s per instance, so the fallback cannot fit a synchronous turn either. The decision is:

| | M1 (base M, `sim`, development) | M2 staging (base P, synchronous) | M3 asynchronous (staging first, then production) |
|---|---|---|---|
| Deadline | 180 s after admission (`TURN_DEADLINE_MS`, unchanged) | **100 s from receipt** (pilot `deadlineAt`) | the job's ceiling is **420 s**; the page shows a pending state and reads the result from history |
| Specialist ceiling | 60 s | 20 s (`min(20 s, deadlineAt − now − 5 s)`, the pilot's own rule) | 20 s per call |
| Service checks budget (`budget_ms`) | `min(65 s, deadlineAt − now − 15 s − 2 s)`; refused below `checks_min_ms` 3 s | `min(65 s, deadlineAt − now − 5 s − 2 s)`; refused below `checks_min_ms` 3 s | **240 s** in total (Daniel's four minutes), shared by the original and any revision |
| Worker checks timer | `budget_ms` + 15 s (`checks_tail_ms`) | `budget_ms` + 5 s (`checks_tail_ms`, the settle margin) | protocol 1.1 (D16) |
| Revision (D5) | none | none | at most one, started only if at least 90 s of the formal budget remain |
| Overseer-selected fallback (D17) | exercised in arena rounds only; not on the kit path until protocol 1.1 | **not offered**: incomplete means withheld | `verified-v1-fallback`, at most 120 s (provisional), two independent validated reviews; **off until measured** |
| Worst case (handshake + route + specialist + budget + tail + reserve) | 3 + 5 + 60 + 65 + 15 + 2 = 150 s: 30 s under 180 s, 40 s under the page's 190 s | 3 + 5 + 20 + 65 + 5 + 2 = **100 s** | 20 + 240 + 20 + 120 + margins ≤ 420 s (provisional, D17) |

The 120 s overseer deadline and the 420 s ceiling rest on the standard profile (D30), whose live latency is not
measured; the uncommitted fast profile only targets 30 to 90 s per instance, and the flash pilot measured fast at about
5.6 times faster than standard. Both values are therefore provisional and must be confirmed by measured standard-profile
latency before the fallback enters any allowlist (D17). A miss fails closed (the answer is withheld), is reported, and
is never fixed by relaxing the two-review rule or the 0.90 threshold.

**How the checks stay inside the deadline.** The two values are computed separately, as the kit's
`website/src/verify/with-verification.js` computes them, at the moment of the checks call:
- the service's budget `budget_ms = min(checks_max_ms 65 000, deadlineAt − now − checks_tail_ms − completion_reserve_ms 2 000)`,
  sent in the request; the checks are not called, and the turn is refused with `verifier_timeout` (503
  `checks_incomplete`), when less than `checks_min_ms` 3 000 is left;
- the Worker's client timer `budget_ms + checks_tail_ms`.

So the Worker's timer always ends `completion_reserve_ms` before `deadlineAt`. A slip before the checks call (the
handshake, admission, the Cloudflare D1 database reads, a slow route or specialist) shortens the budget, never the settle margin or the
completion reserve, and a budget too short to run is a withheld answer, never an unchecked one. `COMPATIBILITY.json`
holds `timing.completion_reserve_ms` 2 000 and `timing.bases` `checks_tail_ms` 15 000 for base M and 5 000 for base P
(D25).

**Why this is honest.** No path labels an incomplete check as checked. The synchronous milestones withhold rather than
pretend. The only cost is refusals, which D22 reports as measured. The 240 s budget and the fallback arrive only with a
delivery mode that can actually carry them. **Production** keeps `CHAT_BACKEND=none` until Bruno's own production go,
given after M2 evidence (the "After M2" list that closes this record). When enabled, production first runs the M2 synchronous
configuration, and moves to M3 when M3 has run on staging.

### C. Hosting, caps, data terms and model tiers (D7, D14, D15, D23)

- **Who runs what.** Daniel runs the staging verification service on an external HTTPS container host; development
  and `sim` run it on loopback (D7). Bruno owns the Worker, its secret and its budget module.
- **Spending.** No provider call is paid before owner step 12, when Daniel enables live calls on the service, just
  before staging switches to `verified`. The one earlier cost is the container host, which Daniel builds and configures
  at owner step 8: that is his own spend decision, under its own ceiling of USD 30 a month (D7). The new service caps
  all default to 0; with a live provider and any delivery-path cap at 0, the service refuses to start (`KIT-HS-018
  live_calls_not_enabled`). Asynchronous work without its cap or its key is disabled at start-up and never affects
  delivery (D14). The caps (D14) are ceilings: the service's call and token caps, the separate caps and key for
  asynchronous work, the Worker's turn caps, and a hard limit at the provider on each new staging key. A cap reached
  on the delivery path, the provider's limit included, is a withheld answer (`NOT_ATTEMPTED`, `provider_unavailable`,
  503 `checks_incomplete`), never an unchecked one.
- **Data (D15).** The data that leaves the Worker is already minimised (D15 lists it). The service keeps no bodies.
  The provider terms must allow at most 30 days of retention, matching the website's 30-day delete copy.
- **Models (D23).** Every deployed agent (specialist, translator, fidelity reviewer, combinator, overseer agents) runs on
  the cheapest tier, as Daniel's rule requires. It is the `policy.defaultPrimary` entry of `model-assignment.json`
  version 2026-10-13.1, whose identifier status reads "published model ID, pin exactly". The comparison entry is
  unverified and is not approved, and there is no automatic fallback (that file's own `fallbackRule`). The flash router
  is deterministic and calls no model.

### D. Signing (D12)

HMAC stays for v1. The Worker never holds a key (invariant 22 of the website's integration planning brief,
`docs/handoff/05-integration-planning-brief.md`). In v1 the Worker trusts the authenticated channel
(TLS plus the bearer token), checks the bindings and re-derives the decision. That re-derivation is what makes the
Worker's release safe, not the signature. Ed25519 would let a party without the secret verify a verdict. Nobody needs
that yet, and it adds a dependency. So it is deferred to protocol 1.1, triggered by the first consumer of verdicts off
the service host (an external auditor, or a sidecar overseer on another host).

### E. Overseer, twofold modes and findings after delivery (D18, D19, D22, with D17)

- **Synchronous milestones.** The deterministic overseer core is embedded and gates delivery. Overseer agents run after
  delivery, are advisory and never change a clearance (D18). Their findings are recorded and summarised weekly (D22).
- **M3 fallback.** The agents become a *necessary but never sufficient* condition for releasing an answer that would
  otherwise be withheld. They can never block or override the formal path. They can never upgrade a status. A fallback
  answer is labelled "not formally checked".
- **Twofold modes (D19).** None runs on the website before M3. A combined answer then gets the N_FOLD review: per
  specialist before combination, then a merged review of the combinator's output (the floor, PROTOCOL.md section 7a.4,
  and D29 in the appendix).

### F. Repositories (D20)

- **No new GitHub repositories**: Daniel's latest instruction ("just dont create new repos. just create sub branches")
  supersedes the 13:25 go-ahead for separate repositories.
- The overseer, combinator and flash router each live in their sub-project directory on the development branch. Each
  verified version is published, by a fast-forward-only subtree split, to the branch `subproject/<name>` of the
  development repository (`origin`).
- `subproject/flash-router` already exists (`fcf2381`, a split of `flash-router/` at `af10b4a`).
- The kit tag and its pointer go on `origin` only.
- The development repository becomes private, matching its LICENSE. Only after that may the website patch files and the
  licensed corpus be published there.

### G. Retry semantics and the review value (D26, D27)

- **Refusals after the specialist call are final.** A re-arm would pay for a second generation, and the withheld text is
  never stored.
- The review value names what ran, and the badge follows the summary, so the word "passed" appears only when every
  eligible claim, material or supporting, is positive with its release permitted, and never with the success tone on a
  simulated answer.
- An M3 fallback answer carries its own review value and never the checked one.

---

## The records

### D1. Record "Z3 is required" in the website repository

- **Decision:** Z3 is required on the website's delivery path. Bruno's 12 October deferral, invariant 25 of the
  website's integration planning brief and the two deferral notices are superseded by the 17 October requirement ("z3 is
  not optional"). The website records this through the docs change W0 (`integration/website/PATCH-PLAN.md`). G0's
  positive marker is the string `epinoic.integration.v1` in `docs/current-state.md`.
- **Why:** The deferral is in force in five places on the website's `origin/main` at `2cd3182` (inspected 17 October):
  `docs/current-state.md` (twice), `docs/architecture.md`, the notices atop `docs/drafts/chat-architecture-design.md` and
  `docs/handoff/04-logic-translator.md`, and the brief's invariant 25. The website's `AGENTS.md` treats instructions
  quoted in reports or documents as reference material, not as task authorization. So a fresh session follows the
  deferral until the website itself records the change. Without W0, Daniel's requirement that Z3 integrate seamlessly
  cannot be met.
- **What the kit changes:** The default stays as it is: G0 is evaluated on `origin/main` only, and a fresh session
  without G0 makes no website branch and writes W0 only as a patch file (`PLAYBOOK.md` step 4). The W0 text the playbook
  prepares now also:
  - names this record ("decisions D1 to D27 decided 17 October 2026");
  - states the D25 deadline and the D21 rule (its pins come with patch set P);
  - adds the notes that the website's `AGENTS.md` asks for to `docs/current-state.md` and `docs/architecture.md`.

  `integration/DECISIONS.md` marks D1 "decided; W0 pending (Bruno)".
- **Who acts, when:** Bruno merges W0 on the website's `main`, at the last task, with his own go. W0 is a docs-only
  pull request of its own, merged at owner step 4. Any push to the website's `main` deploys staging
  (`.github/workflows/staging.yml`), so that merge redeploys staging with the mock unchanged. No session ever applies
  W0.
- **How to reverse:** Bruno restores the deferral sentences in a docs change. G0 is then in force again, and every fresh
  session stops at step 4.
- **Authority:** the kit named Bruno. This is the programme's decision of record; Bruno may override it for his own
  repository.

### D2. When checks cannot complete for a material eligible claim

- **Decision:**
  - **Staging and production:** withhold the answer (`verified-v1`): 503 `checks_incomplete`, final.
    INVALID_FORMALIZATION on a material eligible claim now counts as an incomplete check, alongside UNKNOWN, TIMEOUT,
    INTERNAL_ERROR and NOT_ATTEMPTED.
  - **`verified-v1-qualify`** (release labelled "Check unavailable") is allowed only where `service_env` is
    `development` or `sim`.
  - **M3:** `verified-v1-fallback` (D17) may replace the withholding only after its measurement.
- **Why:**
  - Daniel's delivery rule withholds an answer that is neither formally checked nor overseer-selected.
  - With no synchronous fallback (D17), withholding is the only honest synchronous outcome.
  - INVALID_FORMALIZATION means that the cheapest-tier translation of an eligible claim failed validation. Like a
    failed translation, which the kit already reports as INTERNAL_ERROR, that is a check that did not complete, not a
    claim beyond the encoding. UNSUPPORTED and NOT_ELIGIBLE stay qualified (section A).
  - More refusals are the accepted cost, and they are measured (D22).
  - `PROTOCOL.md` section 8 currently says INVALID_FORMALIZATION neither blocks nor leaves the checks incomplete. This
    decision changes that before the first kit tag (see D3 on when `verified-v1` is fixed).
- **What the kit changes:**
  - **Decision table** (`delivery.decide`, `website/src/verify/decision-table.js`): row 5 adds INVALID_FORMALIZATION.
    New vector `decision-table/row5-invalid-formalization.json` (refuse under `verified-v1`), and a qualify-policy
    twin that continues with the label "Not formally checked".
  - **Policies by environment:** `COMPATIBILITY.json` gains
    `"verdict_policies_by_env": {"development": ["verified-v1", "verified-v1-qualify"], "sim": ["verified-v1", "verified-v1-qualify"], "staging": ["verified-v1"], "production": ["verified-v1"]}`.
    - The service refuses a policy outside its environment's list with KIT-REQ-003 `policy_unknown`.
    - `capabilities.policies` lists only the allowed ones.
    - The Worker's `verification.js` refuses a capabilities response that offers qualify on a hosted environment
      (`kit_hs_mismatch`).
    - `with-verification.js` keeps `verified-v1` as its only default.
    - `verified-v1-fallback` (D17) is not in any v1 list. It joins the `sim` and `development` lists when protocol 1.1
      is built, and a hosted list only after its measurement (D17).
  - Generated files are regenerated: `compat.py`, `compat.js`, the schemas, the vectors and the MANIFEST.
  - `PROTOCOL.md` section 8 row 5 and the sentence after the table (INVALID_FORMALIZATION moves from the qualified
    statuses to row 5), and `DECISIONS.md`.
- **Who acts, when:** nobody: the kit implements it.
- **How to reverse:** a new kit tag that lists `verified-v1-qualify` for an environment in `verdict_policies_by_env`.
  The decision-table rows do not change.
- **Authority:** the kit named the founder with Bruno. This is the programme's decision of record; Bruno may override it
  for his own repository.

### D3. Negative definitive results on a material claim

- **Decision:** COUNTEREXAMPLE, INCONSISTENT_PREMISES and UNSATISFIABLE on a material claim of the deliverable block it:
  422 `review_unresolved`, final, with reasons KIT-DL-010 and KIT-DL-002, -007 and -008 as now. This includes a
  COUNTEREXAMPLE that carries only the advisory W110/W111. A negative result on a supporting claim does not block,
  which is unchanged (vector `deliver-with-supporting-blocking-claim`).
- **Why:**
  - Consistency before entailment: a refuted encoding of a material claim is the strongest signal the engine gives.
  - W110 and W111 say the encoding may be weak, but nothing tells a weak encoding from a wrong claim.
  - Showing the answer would mean either labelling a refuted claim or hiding the refutation. Withholding misleads no one.
  - False refusals are measured on staging (D22), and the M3 revision (D5) is the remedy, not a weaker rule.
- **What the kit changes:** nothing. Row 4 already blocks. `DECISIONS.md` marks D3 decided, and `PROTOCOL.md` section 8
  states that W110/W111 do not soften row 4.
- **Who acts, when:** nobody: the kit implements it.
- **How to reverse:** a new kit tag with a policy whose row 4 releases a W110/W111-only COUNTEREXAMPLE with a label. That
  is a new policy name.
- **When `verified-v1` is fixed:** `verified-v1` is fixed at the first kit tag, `integration-kit-v1`. D2 (row 5 gains
  INVALID_FORMALIZATION) and D4 (row 6 refuses) define it before that tag; no tag exists yet (inspected), so no stored
  verdict carries an earlier meaning. After the tag, any change to what a policy decides needs a new policy name.
- **Authority:** the kit named the founder. This is the programme's decision of record; Bruno may override it for his
  own repository.

### D4. AMBIGUOUS_TRANSLATION on a material claim

- **Decision:**
  - **Staging and production** (`verified-v1`): withhold the answer, with 422 `review_unresolved`, final, and reason
    KIT-DL-012 `ambiguous_material_claim`. The raw code `kit_dl_012` already maps to `review_unresolved`.
  - **`verified-v1-qualify`** (development and `sim` only): continue, labelled "Not formally checked: more than one
    reading".
  - There is no website-authored clarification in v1.
- **Why:**
  - An ambiguous material claim has more than one formal reading, and one of them may be refuted. It has not reached a
    definitive result, so Daniel's rule withholds it, as D2 does.
  - A website-authored clarification needs new contract fields and UI. Under the final-refusal rule (D26) it would also
    need the withheld text, which is never stored.
- **What the kit changes:**
  - Row 6 becomes: under `verified-v1`, `refuse_unresolved` with KIT-DL-012; under qualify, continue. KIT-DL-012 is no
    longer only reserved.
  - Vector `deliver-ambiguous-material-claim-labelled.json` moves to the qualify policy (same expected labels).
  - New vector `row6-ambiguous-default-policy-refuses.json`.
  - `PROTOCOL.md` section 8 row 6, and `website/src/verify/decision-table.js` with its tests.
- **Who acts, when:** nobody: the kit implements it.
- **How to reverse:** a new kit tag with a policy that continues on row 6. The label copy already exists.
- **Authority:** the kit named the founder with Bruno. This is the programme's decision of record; Bruno may override it
  for his own repository.

### D5. Bounded revision

- **Decision:**
  - **Synchronous delivery (M1, M2):** no revision; `revise` is never produced.
  - **Asynchronous delivery (M3):** at most one revision per turn.
    - **Trigger:** row 4 on a material claim, or a receipt error finding.
    - **Feedback:** the revision notice is built by code from finding codes and claim excerpts only, never agent text.
      This is Daniel's specialist-feedback function, in the form the overseer feedback design allows: trusted sources
      only; never steering toward entailment, inventing premises, widening numbers or dropping claims.
    - **Re-check:** the revision is re-checked in full, and a second `revise` becomes `refuse_unresolved` with
      KIT-DL-020.
    - **Time:** it starts only if at least 90 s of the 240 s formal budget remain.
    - **Cost:** it reserves one more specialist generation in the turn's budget (D14).
- **Why:**
  - At 100 s, a second specialist call plus a second checks call (20 + 65 s) does not fit (section B).
  - At 240 s it does, and a revision is the remedy for the false refusals that D3 accepts.
  - On base P a revision is a second paid generation, so it needs a budget reservation (D14).
- **What the kit changes:**
  - No change for v1 policies.
  - The M3 policy `verified-v1-fallback` (D17) allows one revision. Protocol 1.1 adds
    `limits.revision_min_budget_ms: 90000`.
  - `PROTOCOL.md` section 10 states the M3 rule.
- **Who acts, when:** nobody now. At M3, Bruno approves the extra generation in the website's budget module (D14) as
  part of the M3 website change.
- **How to reverse:** a policy without revision, which is every v1 policy.
- **Authority:** the kit named the founder with Bruno (budget). This is the programme's decision of record; Bruno may
  override it for his own repository.

### D6. A cheapest-tier fidelity reviewer

- **Decision:** Wire the translator's existing advisory `SemanticReviewer` (`translate/review.py`) through the
  cheapest-tier provider. The reviewer runs as a separate call: it never sees the translator's chain of reasoning.
  Its evidence is exactly what `build_review_request` (`translate/review.py`) already assembles from what the service
  holds: the claim and its supporting claims, the translation's problem and interpretation record, the premise sources,
  figure readings and diagnostics, and the specialist report and task record that the service builds from the
  student's current message and the answer. The website has no supplied texts in v1, so none are shown. The
  specialist's knowledge bundle never leaves the Worker (D15), so it never reaches the service, the reviewer or the
  provider. At most 8 reviews per answer (one per translated claim).

  Modes, set by the new `EPINOIC_FIDELITY_REVIEW`:

  | Mode | Behaviour |
  |---|---|
  | `off` (default) | as today: `fidelity: missing` |
  | `shadow` | the reviews run **after the TurnVerdict is signed and returned**, on the same asynchronous queue as the overseer agents. They use no translation slot and none of the checks budget, are never awaited by a turn, and draw only on their own cap, `EPINOIC_FIDELITY_REVIEWS_PER_DAY` (default 0), and on the asynchronous-work provider key `EPINOIC_ASYNC_ANTHROPIC_API_KEY` (D14), never on the delivery path's caps or key. With that cap at 0 or that key missing, the service still starts, shadow reviews are disabled with a metadata-only start-up notice, and deliveries are untouched (D14). Their inputs are held in memory only until the review ends (D15). The verdict is unchanged by construction: `fidelity` stays `missing` and `release_permitted` stays false. Results are logged as metadata only (D22) |
  | `on` | the reviews run in parallel with Z3 inside the checks budget, in the translation slots, and count in the delivery path's caps; the review decides `fidelity`, so `release_permitted` can become true under `outcome.assess_release` |

  - **Development and `sim`:** `on`, with fixture reviews from the corpus, so that the `formally_checked` labels are
    exercised. `translation.reviewer` is then `fixture`, the answer is `simulated`, and its badge reads "Automatic
    checks passed (simulated)" without the success tone (D13, D27): a fixture verdict is not a review. A hosted `on`
    uses the live provider only; preflight refuses a `fixture` reviewer on staging or production (`KIT-HS-017`).
  - **Staging:** `shadow`.
  - **Production:** `off`.
  - **Switching `on` on a hosted environment** requires the precision of the reviewer's `faithful` verdicts, judged
    blind by the strongest tier on translations from the arena rounds and the sealed hold-out corpora (never student
    data, and never staging content, which the service does not retain, D15), to have a **95% Wilson lower bound of at
    least 0.98** (Daniel's fidelity target). That needs at least 189 `faithful` verdicts with none wrong; the record requires at
    least 200 (none may be wrong at 200; at most 1 at 300, 2 at 400, 3 at 500). D17 uses the same rule with its own
    threshold. Then a new kit tag lifts the refusal.
- **Why:**
  - Without fidelity review, nothing can be labelled formally checked: `release_permitted` needs a faithful,
    evidence-bound review. Daniel's formal path labels an answer `formally_checked` only when its claims are clean.
  - A model's "faithful" is advisory (the module says so). Letting it upgrade a hosted label before it is measured would
    trust an unmeasured agent judgement.
  - Shadow mode measures on staging, as metadata only, what the offline corpora cannot: the reviewer's live latency,
    cost, failure rate and verdict distribution. It does so at a bounded cost, and only after the verdict exists. The
    precision itself is measured offline, where ground truth exists. Running shadow reviews inside the checks budget would let it delay translations into `NOT_ATTEMPTED skipped_budget` or use up the daily call cap, and
    so change outcomes; running it after signing, under its own cap and key, cannot.
  - A Wilson lower bound, not a point estimate, is used because at 200 verdicts a point estimate of 0.98 has a lower
    bound of only about 0.95.
- **What the kit changes:**
  - `settings.py`: `EPINOIC_FIDELITY_REVIEW` (`off`, `shadow` or `on`; default `off`) and
    `EPINOIC_FIDELITY_REVIEWS_PER_DAY` (default 0; staging value 200, D14).
  - `preflight.py`: refuses `on` when `service_env` is `staging` or `production` with a new closed code,
    `KIT-HS-017 fidelity_review_unmeasured`, in kit v1. `errors.py` and `PROTOCOL.md` section 12 gain the code.
  - `protocol.py`: `translation.reviewer` becomes `none`, `fixture`, `shadow` or `live`, replacing the `none`-only
    literal. The schemas and the handshake vectors are regenerated.
  - `turn.py`: wires the reviewer into the task-aware verifier for `on`, and enqueues shadow reviews only after the
    verdict is signed.
  - New tests: shadow mode never changes a verdict byte, run with a slow fake provider and with the delivery path's
    call cap one call from exhaustion, and with the shadow cap exhausted (the verdict bytes equal those with `off`); a
    shadow review is never awaited by the turn; `on` in `sim` reaches `formally_checked` on the corpus; preflight
    refuses `on` when hosted, and a `fixture` reviewer when hosted (`KIT-HS-017`); a review request built for a
    verified turn carries no supplied text and nothing outside the fields listed above.
  - `PROTOCOL.md` section 5.3, and `DECISIONS.md`.
- **Who acts, when:** the kit implements shadow mode. After M2, Daniel records the measurement in `DECISIONS.md`
  under a new kit tag and sets `EPINOIC_FIDELITY_REVIEW=on` on the staging service host. Production follows with
  Bruno's production go.
- **How to reverse:** set `EPINOIC_FIDELITY_REVIEW=shadow` or `off` on the service host. Labels fall back to "encoding
  only" at once, and stored answers are replayed unchanged. To stop shadow spending alone, set
  `EPINOIC_FIDELITY_REVIEWS_PER_DAY=0`: shadow reviews stop and deliveries continue (D14).
- **Authority:** the kit named the founder (Daniel). Decided under his delegation.

### D7. Hosting

- **Decision:**
  - **M2 (staging):** an external Linux container host over HTTPS with a bearer token, operated by Daniel. It runs the
    kit image `integration/deploy/container/Dockerfile`, built from the kit tag, as its non-root user `epinoic`.
  - **One deployment per environment:** development (loopback), `sim` (loopback, in the simulation), staging (hosted),
    and production (not deployed in M2). Each has its own token and keys.
  - **Capacity:** 1 instance; `EPINOIC_MAX_CONCURRENCY=4`; `EPINOIC_RATE_PER_MINUTE=60`;
    `EPINOIC_MAX_BODY_BYTES=1000000`; at least 3 GiB of memory and 2 vCPU.
  - **Host requirements:** a secret store for environment variables, TLS-terminated HTTPS, and no logging of request
    bodies by the host (D15).
  - **Hosting cost:** Daniel's own spend decision at owner step 8, under a ceiling of USD 30 a month for the staging
    host: a fixed-price plan, or a host-side spending cap at that amount. Where the host offers neither, a billing alert
    at that amount, and Daniel stops the container when it fires. This ceiling is never raised by a programme step.
  - **After M2:** the Cloudflare Container behind a Worker binding is the target hosting. It moves to Bruno's account,
    with the deliberate change to the staging-keys pin, and only after M2 has run.
- **Why:**
  - Z3 cannot run in a Worker: workerd has no `Worker` constructor, `Atomics.wait` throws, and an isolate is capped at
    128 MB (translator `docs/AUDIT.md`).
  - External HTTPS adds no binding beyond PR S's `CHAT_DB`, so M2 changes the staging-keys pin only once, through PR S.
  - The service accepts exactly one bearer token per process (`settings.py`), which means one deployment per
    environment.
  - The daily caps (D14) keep traffic far below 60 calls a minute.
  - Memory: Z3's `memory_max_size` is process-wide, and the engine sets it to 512 MB times the verifications running
    at once (`engine/procedures.py`, `apply_global_memory_limit`; the design's "512 MB per verification,
    process-wide"). With four verifications at once that is 2 GiB for Z3 alone, so 3 GiB is the floor that leaves
    headroom for the Python process, the embedded overseer and the asynchronous queue. A Z3 memory abort gives
    UNKNOWN, which withholds the answer when the claim is material (D2) and is never labelled checked.
  - A host without a spending ceiling would be the one cost outside the D14 caps.
  - The non-root user is required for the router boundary on hosted environments (D28), even while the router is
    detached.
- **What the kit changes:**
  - `deploy/container/README.md` records these values, the hosting ceiling, and `TRANSLATOR_MODE=http` for staging.
  - `readiness/check.py --live` lists the host requirements as owner rows: names only, no values.
  - The `binding` transport stays built and tested, unused.
- **Who acts, when:** at the last task:
  - Daniel builds the staging image and sets the service variables by name on the host (owner step 8), and starts it
    only once live calls are enabled (owner step 12).
  - Bruno sets `TRANSLATOR_SERVICE_TOKEN` on the staging Worker (`wrangler secret put`, which deploys).
  - Bruno merges `TRANSLATOR_MODE=http` and `TRANSLATOR_BASE_URL` for staging in the final reviewed pull request.
- **How to reverse:**
  - Set staging `TRANSLATOR_MODE=none` through a reviewed pull request. The Worker then refuses verified turns with
    `chat_unavailable` before admission.
  - Stop the container.
  - Bruno deletes the token secret.
- **Authority:** the kit named the founder, Daniel and Bruno. This is the programme's decision of record; Bruno may
  override it for his own repository and his Cloudflare account.

### D8. Who extracts claims

- **Decision:** The translator's branch parsers extract claims inside the service, from the answer as raw text
  (PROTOCOL.md section 5.2). Specialists keep `provenance.claims: null`, pinned by five tests in the agents repository
  (inspected 17 October). The
  website never extracts claims and never decides eligibility.
- **Why:** A claims field inside the runtime would be a reviewed contract bump, and the five pinning tests could not be
  kept as written (no weakening). The parsers already carry the STEM front end and the packs. Keeping extraction in one
  place keeps the arena equivalence gate (G-EQ-ARENA, `integration/sim/gates.py`) comparable with the arena.
- **What the kit changes:** nothing. The specialist port already refuses a non-null `claims` (KIT-REQ-011).
  `DECISIONS.md` marks D8 decided.
- **Who acts, when:** nobody: the kit implements it.
- **How to reverse:** a runtime contract v0.3.0 that fills `claims`, with a new specialist pair in
  `COMPATIBILITY.json`. The service would still re-extract the claims and treat the runtime's as untrusted data.
- **Authority:** the kit named the founder (Daniel). Decided under his delegation.

### D9 / D10. Subjects, slugs and STEM on the website

- **Decision:**
  - **Website routes:**
    - `history` maps to `history` in development, `sim` and staging. It is the only route served on staging.
    - `english` maps to `english-a-literature` in `sim` only, as the built subject map's row says
      (`"environments": ["sim"]`). In development, staging and production it answers `specialist_unmapped` (503
      `chat_unavailable`), because the runtime has no English entry. Development needs no English route: the
      simulation exercises it.
  - **STEM:**
    - No website STEM route before M3.
    - The service requires all three STEM branches at start-up (KIT-HS-005) and checks STEM for the agents driver and
      the simulation.
    - When Bruno schedules W7, the programme recommends an additive migration that keeps the legacy `route_id` CHECK and
      adds no table rebuild. That migration is Bruno's design.
  - **Spanish:** `spanish-b` is the canonical slug. `language-b-spanish` stays a service-only alias, as the subject map
    already has it.
- **Why:**
  - The agents repository's runtime manifest has one entry, `history` (inspected 17 October).
  - The website's subjects are a closed pair (`CHECK (route_id IN ('english','history'))` in
    `migrations/0001_chat_state.sql`), and a third needs a table rebuild that the migration pins in
    `tests/migrations.test.js` forbid.
  - `english-a-literature` is the subject map's existing `sim` mapping, and it is what `check_answer.py` calls
    "English A: Literature".
  - Keeping the map as built avoids a new map version, digest and kit tag for a route that has no specialist.
- **What the kit changes:** none to `subject-map.json` (version 2026-10-17.2, unchanged digest): its English row already
  reads `"environments": ["sim"]`. The row stays `provisional: true` until an English specialist exists in the runtime.
  `DECISIONS.md` marks D9/D10 decided.
- **Who acts, when:** nobody: the kit implements it. Bruno decides when W7 happens, and its migration is his.
- **How to reverse:** a new subject-map version (a new digest and a new kit tag) that adds environments to a row.
- **Authority:** the kit named Bruno with Daniel. This is the programme's decision of record; Bruno may override it for
  his own repository.

### D11. Identifier mapping

- **Decision:** `task_id` = turnId; `request_id` = attemptId; `plan_id` = `plan-` + attemptId; `report_id` and
  `agent_id` as in PROTOCOL.md section 2. `X-Request-Id` is a log label only.
- **Why:** turnId is stable across retries and re-arms, while attemptId fences each attempt's checks (PROTOCOL.md
  section 2). The website's ID pattern is a subset of the protocol's, so no mapping function is needed (checked in the
  pre-build).
- **What the kit changes:** nothing. `DECISIONS.md` marks D11 decided.
- **Who acts, when:** nobody: the kit implements it.
- **How to reverse:** a new protocol major version. Ids are bound into every verdict.
- **Authority:** the kit named Bruno. This is the programme's decision of record; Bruno may override it for his own
  repository.

### D12. Signing the verdict

- **Decision:**
  - **v1 signing:** HMAC-SHA256.
  - **Keys:** three distinct secrets of at least 32 random bytes each, all different: the engine signing key, the
    verdict key and the overseer secret (preflight already refuses equal or short keys, KIT-HS-007 and KIT-HS-008).
  - **Key ids:** dated, for example `engine-202610`, `verdict-202610`.
  - **Rotation:** every 90 days, and at once on any suspected exposure.
  - **The Worker** trusts TLS plus the bearer token, checks the bindings and re-derives the decision. It never claims to
    have verified the HMAC.
  - **Ed25519** verdict signing is deferred to protocol 1.1. It is adopted when the first consumer of verdicts off the
    service host appears: an external auditor, or a sidecar overseer on another host.
- **Why:**
  - Invariant 22 of the website's integration planning brief keeps keys out of the Worker.
  - The Worker's safety comes from the binding checks and the re-derivation (PROTOCOL.md section 9, conditions 6 and 10
    to 13), which a forged signature could not pass anyway without matching every bound digest.
  - Within the service, the overseer trusts only signed engine results, and HMAC does that.
  - With HMAC the overseer must hold the engine secret. That exposure is limited by its trust rule that it holds engine
    keys only to verify and signs under its own subkeys, and by the overseer staying embedded on the same host (D18).
  - Ed25519 would add a Python dependency for no current consumer.
- **What the kit changes:**
  - `deploy/container/README.md` and `rollback/ROLLBACK.md` add the rotation procedure: set the new key ids, restart,
    and let the handshake cache refresh within 60 s. Verdicts are not re-signed; stored results are replayed as they
    are.
  - `PROTOCOL.md` section 5.4 keeps the signature scope sentence. `DECISIONS.md` marks D12 decided.
- **Who acts, when:** at the last task, Daniel generates the staging keys in the service host's secret store. No key
  ever reaches the Worker, a repository, a log or a chat.
- **How to reverse:** none is needed for HMAC. Adopting Ed25519 is a protocol minor version with its own vectors.
- **Authority:** the kit named the founder (Daniel). Decided under his delegation.

### D13. Display copy and the `simulated` semantics

- **Decision:** Adopt the kit's proposals as they stand in the patch blocks and the vectors
  (`vectors/chat-contract/labels.json`):
  - **Per-claim labels:** as in PROTOCOL.md section 8 and `vectors/chat-contract/labels.json`.
  - **Scope statement:** the engine scope statement, shown once per answer whenever a formal status is shown.
  - **Banned words:** no label ever says "verified", "true", "proven" or "Reviewed".
  - **Checks box title:** "Automatic checks of the logic encoding".
  - **`simulated`:** true unless the specialist and the checks are both live. The specialist is live when its
    provider is live. The checks are live when the translations, and the fidelity reviews when D6 is `on`
    (`translation.reviewer` is `live`), come from a live provider on a service whose `service_env` is `staging` or
    `production`; fixture translations or fixture reviews make the checks simulated, although Z3 itself always runs.
    Anything other than an explicit `false` counts as simulated. The kit object carries the two parts separately
    (`kit.specialistLive`, `kit.checksLive`), so the copy can name which part is simulated.
  - **Simulated badges:** a simulated answer's badge carries the suffix " (simulated)" and never the success tone, so
    "Automatic checks passed (simulated)" from a fixture fidelity verdict is never shown as a success: a fixture
    verdict is not a review.
  - **Disclosure copy**, true of every answer that any decision releases (including a `not_formally_checkable` answer,
    an answer with an eligible supporting claim that is not positive, and, in development and `sim`, a qualify-policy
    answer). Rows 4 and 5 gate material claims only, so the copy promises formal checking for the main claims only:
    - M1, whose lead names the simulated part: "Prototype — simulated specialist." when only the specialist is
      simulated, "Prototype — simulated checks." when only the checks are, and "Prototype — simulated specialist and
      checks." when both are. It continues: "Answers are shown only after automatic checks allow them. Where a main
      claim of an answer can be expressed in logic, its logic encoding is formally checked; supporting statements may
      not be. Each answer's badge says what was checked. Some checks may be unavailable in this prototype."
    - M2 staging, once both parts are live: "Pilot — answers come from an AI specialist and are shown only after
      automatic checks allow them. Where a main claim of an answer can be expressed in logic, its logic encoding is
      formally checked; supporting statements may not be. Each answer's badge says what was checked. The checks cover
      the logic encoding only; they are not a teacher's review."
- **Why:**
  - The website's current disclosure says no AI model, router or reviewer is called (`public/chat.js`, inspected 17
    October), which would be false under `verified`.
  - The page-level copy must hold for every released answer. Under D2 an answer whose material claims are all
    NOT_ELIGIBLE or UNSUPPORTED is released as `not_formally_checkable`, and under the qualify policy an answer may
    carry "Check unavailable". Copy saying that answers "pass formal checks" would show those as a success. The adopted
    copy says only that checks allowed the answer and that the badge says what was checked; the badge (D27) carries the
    per-answer truth.
  - Rows 4 and 5 count material claims only, so a released answer may carry a supporting claim that is UNKNOWN,
    TIMEOUT, NOT_ATTEMPTED or even COUNTEREXAMPLE (kit vectors `row5-supporting-claim-does-not-count` and
    `deliver-with-supporting-blocking-claim`). Copy promising that every expressible claim is formally checked would
    then be false; the adopted copy promises it for the main claims and says that supporting statements may not be
    checked. The badge cannot read "passed" on such an answer (D27).
  - A fixture fidelity verdict, like the website's mock `passed`, is not a review, so a simulated badge has no success
    tone. In development a live specialist under the local test gate can run against fixture checks, so a fixed
    "simulated specialist" lead would be false there; the lead names whichever part is simulated.
  - "Simulated" must be truthful (the website's truthful-disclosure rule).
  - The scope statement must be kept (the translator repository's safety rules).
  - The M2 sentence adds the scope limit, so that a positive formal result is never read as fact-checking.
- **What the kit changes:**
  - The verified-mode disclosure block (W4) gains the M2 variant, selected when `outcome.kit.simulated === false`, and
    fails closed exactly as now.
  - The M1 copy in the disclosure block is replaced by the copy above, with its three leads selected from
    `kit.specialistLive` and `kit.checksLive` (`with-verification.js` sets both, and `simulated` stays their
    conjunction's negation); a missing flag counts as simulated.
  - `checksBadge` drops the success tone whenever the " (simulated)" suffix applies.
  - New vector entries for the M1 disclosure (each of its three leads) and the M2 disclosure, and disclosure vectors
    for a `not_formally_checkable` answer, for a qualify-policy answer (`incomplete`, "Some checks unavailable"), and
    for the two supporting-claim cases: all material claims positive and permitted with an eligible supporting claim
    UNKNOWN, and the same with a supporting COUNTEREXAMPLE (both `partly_checked`, "Partly checked", D27). Each asserts
    that the page shows no "passed" and no success tone, that the badge matches the summary, and that the scope
    statement appears whenever a formal status is shown (`tests-website/verify-disclosure.test.js`). A further vector
    asserts that a simulated `formally_checked` answer shows "Automatic checks passed (simulated)" with no success tone.
    The same cases are added to `vectors/chat-contract/labels.json`.
  - `DECISIONS.md` marks D13 decided.
- **Who acts, when:** Bruno merges the copy with patch set P, in the reviewed pull request at the last task.
- **How to reverse:** a copy-only website change by Bruno. The closed statuses and vectors keep the meaning, so the copy
  may be reworded but never upgraded.
- **Authority:** the kit named Bruno. This is the programme's decision of record; Bruno may override it for his own
  repository.

### D14. Budgets and caps

- **Decision:** All values are **ceilings**. No provider call is paid before owner step 12, when the owner enables live
  calls, and no programme step ever raises a limit. The container host's cost is Daniel's own spend decision at owner
  step 8, under its own ceiling of USD 30 a month (D7).

  **Website, staging, in base P's budget module (website task 04):**
  - 100 verified turns a day in total, and 20 per principal a day;
  - at most 3 attempts per turn (existing);
  - one specialist generation per attempt (the runtime calls its callback at most once), with the pilot's own
    per-generation limits unchanged;
  - one checks call per attempt;
  - a per-isolate concurrency limit of 4 in the checks client.

  **Verification service, staging (new settings, every default 0, which fails closed):**

  | Setting | Value | Draws on it |
  |---|---|---|
  | `EPINOIC_PROVIDER_CALLS_PER_DAY` | 2,000 | delivery-path calls only: translations, and fidelity reviews in `on` mode |
  | `EPINOIC_INPUT_TOKENS_PER_DAY` | 20,000,000 | the same calls, from the provider's reported usage |
  | `EPINOIC_OUTPUT_TOKENS_PER_DAY` | 2,000,000 | the same calls |
  | `EPINOIC_OVERSEER_REVIEWS_PER_DAY` | 25 | asynchronous overseer-agent reviews only |
  | `EPINOIC_FIDELITY_REVIEWS_PER_DAY` | 200 | asynchronous shadow fidelity reviews only (D6) |

  Per answer on the delivery path: at most 4,000 output tokens per call; at most 8 translated claims, at most 4 in
  flight; per claim, the pipeline's one retry and the provider's one transient retry, so at most 32 calls; plus at most
  8 fidelity reviews in `on` mode only (D6). The worst case is 32 cheapest-tier calls per answer under `off` or
  `shadow`, and 40 under `on`.

  **Two service keys, both named.** Delivery-path calls (translations, and fidelity reviews in `on` mode) use the
  staging verification key, set as `EPINOIC_ANTHROPIC_API_KEY`. Asynchronous work (overseer agents and shadow fidelity
  reviews) uses a second, separate key, set as `EPINOIC_ASYNC_ANTHROPIC_API_KEY`, so that it can never use up the
  delivery path's caps or its provider limit. The provider class receives its key explicitly from the service: one
  client is built from each setting, and neither reads the SDK's default environment variable. On a hosted
  environment preflight refuses to start while that default variable is set (`KIT-HS-009`), so no call can run under a
  key the record does not name. Both settings are secrets: kept out of `repr`, never logged, printed or returned.

  **Asynchronous work never takes delivery down.** When `EPINOIC_OVERSEER_AGENTS=async` or
  `EPINOIC_FIDELITY_REVIEW=shadow` is set and its own cap is 0, or `EPINOIC_ASYNC_ANTHROPIC_API_KEY` is missing,
  preflight still starts the service. It records that asynchronous mode as disabled: every verdict carries
  `review.queued: false` for it, capabilities report it as off, and one metadata-only start-up notice,
  `async_work_disabled`, names the setting (names only, no values). Deliveries are untouched. A cap reached during the
  day, or the asynchronous key's provider limit, drops the remaining asynchronous reviews (counted as dropped, D22) and
  never touches a delivery.

  **Provider hard limits** (set in the provider console before the first live call, each on a new key): USD 20 a month
  on the staging verification key and USD 5 a month on the staging asynchronous-work key (Daniel; together the USD 25
  that the earlier draft of this record gave the single service key, so no ceiling grows), and USD 25 a month on the staging specialist key (Bruno, website task 03).

  **Binding order.** The provider's monthly hard limit is expected to bind first, well before the daily caps; then the
  daily token caps (input, then output); then the daily call cap. Whichever binds, the result on the delivery path is
  the same: the provider or the service gives no translation, the claim is NOT_ATTEMPTED `provider_unavailable`, and
  the answer is withheld (503 `checks_incomplete`). It is never released unchecked.

  **The monthly limit is the spending ceiling; the daily caps stop a runaway day.** One day at the daily caps can cost
  more than a month's hard limit, so the record states the consequence plainly: once the delivery key's hard limit is
  reached, **every staging verified turn is withheld until the provider's monthly reset**. That is a fail-closed
  outcome, never an unchecked answer, and the D22 summary reports the date the limit was reached and the refusals
  counted from then. The asynchronous key's limit only stops asynchronous reviews. Daniel may lower any daily cap at
  any time to spread the month (lowering is always allowed); the programme does not tune them now (no optimisation
  work).

  **Production:** zero. No key, no calls, `CHAT_BACKEND=none`.

  **Form of W5:** a `checks` reservation kind in base P's `src/budget/`, reserved at admission and within the
  36-statement pin. Parallel `usage_daily` columns are not used. W5 needs a migration only if base P's schema
  (`migrations/0003_generation_budget.sql`) constrains its reservation kinds, for example with a `CHECK`; otherwise it
  needs none. Patch set P's author settles which by reading base P when it is built.
- **Why:**
  - Daniel's rule: never raise a spending limit, and keep caps conservative.
  - These caps are also the honest fail-closed point. A cap reached becomes NOT_ATTEMPTED `provider_unavailable`, which
    withholds the answer (D2) and never releases it unchecked.
  - 100 turns a day at the worst case of 32 calls would exceed 2,000 calls, so a daily service cap binds before the
    website's turn cap, by design; the provider limit binds earlier still. Refusals are counted (D22).
  - Input tokens were uncapped. Each cheapest-tier call carries what the translator's renderer puts in it (the claim,
    its supporting claims and the subject profile, design section 2.8), and in `on` mode the review request (D6); the
    specialist's knowledge bundle is never part of it (D15). Their live size is not measured, so input tokens get a
    plain ceiling of their own, which fails closed like the others.
  - A separate key and separate caps for asynchronous work keep advisory work from changing any delivery outcome
    (D6, D18). For the same reason a missing asynchronous cap or key disables only the asynchronous work: refusing to
    start would let advisory settings withhold every staging turn, and would make lowering an advisory cap to 0 take
    delivery offline.
  - The current Anthropic provider builds its client from the SDK's default environment variable
    (`translate/providers/anthropic_provider.py`, `_make_client`). Two keys in one process need two explicitly named
    settings, and refusing the default variable on hosted environments keeps every call on a named, capped key.
  - The budget module already exists in base P (`src/budget/`, website pull request #21). One reservation kind avoids
    a second accounting scheme.
- **What the kit changes:**
  - `settings.py` adds the five settings and the two key settings, `EPINOIC_ANTHROPIC_API_KEY` and
    `EPINOIC_ASYNC_ANTHROPIC_API_KEY`, to its table (names only) and to its secret names, with metadata-only counters
    that reset at 00:00 UTC.
  - `translate/providers/anthropic_provider.py`: the client is built from a key passed explicitly by the service,
    never from the SDK default; `turn.py` builds the delivery-path provider from `EPINOIC_ANTHROPIC_API_KEY` and the
    asynchronous provider from `EPINOIC_ASYNC_ANTHROPIC_API_KEY`.
  - `preflight.py` refuses to start with a live provider when any of the three delivery-path caps (calls, input tokens,
    output tokens) is 0, with a new closed code `KIT-HS-018 live_calls_not_enabled`, and when
    `EPINOIC_ANTHROPIC_API_KEY` is missing or the SDK default variable is set on a hosted environment (`KIT-HS-009`).
    `errors.py` and `PROTOCOL.md` section 12 gain KIT-HS-018. For asynchronous work it never refuses: it disables the
    mode and logs `async_work_disabled`, as above.
  - `readiness/check.py --live` gains owner rows for both key settings and the five caps: whether each is set, names
    only, never a value.
  - `turn.py` makes the verifier return no outcome once a cap is reached (`provider_unavailable`), and maps a provider
    spending-limit or quota error to the same, with no retry.
  - New tests: each cap reached gives NOT_ATTEMPTED `provider_unavailable` and a withheld answer; a fake provider's
    spending-limit error does the same; asynchronous work never decrements a delivery-path counter; with
    `EPINOIC_OVERSEER_AGENTS=async` or `EPINOIC_FIDELITY_REVIEW=shadow` and its cap 0, or the asynchronous key
    missing, a hosted service starts, logs `async_work_disabled` once, queues no review, and returns verdict bytes equal
    to those with the mode off; the delivery-path and asynchronous providers are built from their own named settings,
    and preflight refuses the SDK default variable on a hosted environment.
  - Patch set P adds the `checks` reservation kind and its caps as values Bruno approves when he merges.
  - `DECISIONS.md` marks D14 decided.
- **Who acts, when:** at the last task. Bruno approves the website caps by merging patch set P. Daniel sets the service
  caps on the host, and sets the provider-console hard limits on the two new keys before the first live call. Bruno does
  the same for the specialist key. Owner step 12.4 is the owner's enabling of live calls, from the fail-closed 0 to the
  ceilings above; it raises no limit that was ever in force.
- **How to reverse:** set `EPINOIC_PROVIDER_CALLS_PER_DAY=0`, which refuses live service at start-up. To stop
  asynchronous spending alone, set `EPINOIC_OVERSEER_REVIEWS_PER_DAY` or `EPINOIC_FIDELITY_REVIEWS_PER_DAY` to 0, or
  remove `EPINOIC_ASYNC_ANTHROPIC_API_KEY`: that work is disabled at the next start and deliveries continue. Lowering
  a cap is always allowed. No programme step raises a cap above these ceilings; doing so is the owner's own decision, outside
  this programme.
- **Authority:** the kit named Bruno (website task 04) and the founder. This is the programme's decision of record;
  Bruno may override it for his own repository.

### D15. Data terms, retention and the kit corpus

- **Decision:**
  - **What leaves the Worker:** only the student's current message, the answer, the runtime's log-safe projection
    without its `turn` and `usage` members (PROTOCOL.md section 4), digests and ids. Prior turns never leave it (D24),
    and neither does the specialist's knowledge bundle, so no service-side reviewer or agent can be given it (D6).
  - **What reaches the cheapest-tier provider from the service:** what the translator's renderer sends (claim texts,
    supporting claims and the subject profile), and the fidelity reviewer's request built from the same material (D6).
  - **The service:**
    - persists no request or response body;
    - keeps metadata-only logs for at most 30 days;
    - keeps an asynchronous overseer-review dossier, and a shadow fidelity review's inputs (D6), in memory only, until
      the review ends;
    - keeps the evidence tap in `sim` only (KIT-HS-012 elsewhere).
  - **Providers:** the cheapest-tier provider is used, on both service keys (D14), only under terms that exclude
    training on inputs and keep them for at most 30 days (zero retention where the provider offers it).
  - **Who uses staging:** only testers behind Bruno's Access policy, with synthetic or self-written prompts, until Bruno
    records the student-data terms in the website's docs.
  - **The licensed corpus:** recorded arena rounds may ship as `integration/sim/corpus/licensed/`, re-keyed and listed
    by digest. They contain no student data. They ship only after the development repository is private (D20); until
    then the kit carries the synthetic corpus only.
- **Why:**
  - The website's delete copy promises recovery copies for at most 30 days, so no verifier copy may outlive that.
  - The website's rules keep real student text away from providers until data terms are decided.
  - The equivalence gates (G-EQ, `integration/sim/gates.py`) on recorded material, and real translations, need the
    recorded rounds.
  - The only obstacle to shipping them is visibility: the development repository can be cloned publicly although its
    LICENSE says it is confidential.
- **What the kit changes:**
  - `integration/sim/corpus/DATA-TERMS.md` states these terms.
  - `deploy/container/README.md` lists the host and provider terms as owner preconditions.
  - `build_corpus.py` gains `--licensed`, which refuses to write while `COMPATIBILITY.json`
    `repositories.translator_visibility` is not `private` (a new field, default `public`).
  - `DECISIONS.md` marks D15 decided.
- **Who acts, when:** at the last task. Daniel accepts the provider's data terms for the new staging key before enabling
  live calls. Bruno records the pilot's data notice in the website docs (part of W0 or patch set P). Daniel makes the
  repository private (D20), after which the programme may build the licensed subset.
- **How to reverse:** remove the licensed corpus under a new kit tag (published tags stay). Retention can only be made
  shorter.
- **Authority:** the kit named the founder and Daniel. Decided under his delegation.

### D16. Synchronous or asynchronous delivery

- **Decision:**
  - **M1 and M2:** synchronous, within the base's deadline (section B; D25 for base P).
  - **M3:** asynchronous delivery is adopted as the target that carries Daniel's four-minute formal budget, the one
    revision (D5) and the gated fallback (D17).
    - The service side is protocol `epinoic.integration.v1` minor 1.1: `POST /v1/turns/check` with
      `delivery: "async"` answers 202 with a `turn-ticket.v1`, and `GET /v1/turns/check/<request_id>` returns
      `pending` or the signed verdict.
    - The website side is a pending turn state, a background job and a page that reads the result from history. It is
      Bruno's design, written as W9, after M2.
    - The Cloudflare mechanism (Queues, Durable Objects or alarms) must be re-checked against current documentation
      (general).
- **Why:**
  - A 240 s budget exceeds the page's 190 s wait, and the 30 s `waitUntil` window rules out long synchronous work after
    a disconnect (section B).
  - Synchronous delivery is buildable now, and an asynchronous design avoids the 30 s risk (D25's option (c)).
- **What the kit changes:**
  - For v1, one additive schema change, made before the first kit tag: the closed capabilities object gains a required
    field `delivery`, whose v1 value is `["sync"]`. That means `protocol.py`, `schemas/capabilities.v1.schema.json`
    regenerated, the handshake vectors regenerated (every `vectors/handshake/*.json` capabilities fixture gains the
    field, and a new vector refuses a capabilities response without it), `compat.py`, `compat.js`, the Worker's
    `verification.js` validation and the MANIFEST.
  - `PROTOCOL.md` gains a "1.1 (planned)" note describing the asynchronous messages. Nothing else is built until M2 has
    run.
  - `DECISIONS.md` marks D16 decided.
- **Who acts, when:** nobody now. At M3, Bruno designs and merges the website side, and the programme builds protocol
  1.1 in the translator.
- **How to reverse:** stay synchronous. Protocol 1.1 is additive, and `delivery` lists what the service offers.
- **Authority:** the kit named Bruno and the founder. This is the programme's decision of record; Bruno may override it
  for his own repository.

### D17. The delivery-rule parameters

- **Decision:** Daniel's delivery rule is confirmed and given exact terms.
  1. **The formal path.**
     - **Synchronous (M1, M2):** the formal budget is the checks budget of section B, at most 65 s.
     - **Asynchronous (M3):** the formal budget is 240 s.
     - **Outcome:** an answer whose material eligible claims all reach a positive definitive result is delivered
       through the decision table, labelled by its summary.
  2. **The overseer-selected fallback.** Policy `verified-v1-fallback`, asynchronous only.
     - **When it is considered:** only when the formal path ends in `refuse_incomplete` (row 5) or with an ambiguous
       material claim (row 6), and the deterministic review passed, and no material claim has a negative definitive
       result.
     - **Who reviews:** overseer agents built only from the exported pack, on the cheapest tier, standard profile. Each
       candidate gets at least two independent complete reviews (the floor's DUPLICATE 2), each verdict validated by the
       deterministic intake. A candidate is the original answer or its one revision.
     - **Accuracy:** the share of the candidate's material claims that both validated reviews find accurate, with no
       deterministic finding against them. A candidate qualifies only when its accuracy is strictly greater than 0.90.
     - **Choice:** the candidate with the highest accuracy is delivered, with review value `selected:integration.v1`
       (D27) and summary `overseer_selected`. It is never labelled checked, and its unfinished claims keep the "Check
       unavailable" label.
     - **Overseer deadline:** 120 s, provisional (below). If it passes, the answer is withheld.
     - **Provisional timing:** the 120 s deadline and the job's 420 s ceiling assume the standard profile (D30), whose
       live latency is unmeasured; the fast profile, which only targets 30 to 90 s per instance, was measured in the
       flash pilot at about 5.6 times faster than standard. Both values must be confirmed by measured standard-profile
       latency before the fallback enters any allowlist. A miss fails closed, is reported, and is never fixed by
       relaxing the two-review rule or the 0.90 threshold; a different deadline is a new decision under a new kit tag.
  3. **Otherwise the answer is withheld,** with the existing codes.
  4. **"An answer whose required checks did not complete is never labelled checked"** is always on, under every policy.
  5. **Enablement.** The fallback policy enters a hosted environment's allowlist (D2's `verdict_policies_by_env`) only
     after a measurement of its green-light precision, judged blind by the strongest tier on the arena rounds and the
     sealed hold-out corpora (never on student data). The lower bound of its 95% Wilson interval must be at least 0.90,
     over at least 200 green-lit candidates. This is the same rule as D6's (a Wilson lower bound, not a point
     estimate), with the threshold of Daniel's rule, and it also needs the measured latency above. From protocol 1.1
     until then, the policy is listed for `sim` and development only; before protocol 1.1 it is in no list and is
     exercised in arena rounds only (D2).
- **Why:**
  - Daniel's rule, as recorded in the programme's standing instructions: four minutes, above 90%, else withheld, and a
    fallback never labelled checked.
  - It is specified for the programme's delivery step and is to be exercised in arena rounds 8 to 10; it is not
    implemented on any branch yet (inspected 17 October: no local or remote-tracking ref defines `overseer_selected`).
  - Overseer agents are unmeasured live, and even their uncommitted fast profile only targets 30 to 90 s per instance,
    so the fallback needs asynchronous delivery.
  - Agent verdicts are advisory. Using them to *permit* a release that the formal path would withhold needs measured
    evidence, not an assumption. Even then they never upgrade a status and never override a deterministic refusal.
    This keeps "only signed engine results are trusted" for every status and every checked label.
- **What the kit changes:**
  - The policy name `verified-v1-fallback`, the summary `overseer_selected` and the review value
    `selected:integration.v1` are reserved in `protocol.py`, `codes.js` and the vectors.
  - They are implemented with protocol 1.1. The capabilities response omits the policy unless `delivery` includes
    `async` and the environment's allowlist names it; a Worker configured for a policy the capabilities do not offer
    refuses with `kit_hs_mismatch`; and the service refuses a request naming it with KIT-REQ-003 `policy_unknown`.
  - Once the programme's delivery step exists, the fallback's decision vectors must equal its delivery-rule vectors
    (one shared set).
  - `PROTOCOL.md` section 9 states the fallback as a separate path that is never "checked".
  - `DECISIONS.md` marks D17 decided.
- **Who acts, when:** the kit implements it in M3. After the measurement, Daniel records it under a new kit tag that adds
  the policy to staging's allowlist. Production follows with Bruno's production go.
- **How to reverse:** remove the policy from an environment's allowlist with a new kit tag. Answers already delivered
  stay as stored, with their own review value.
- **Authority:** the kit named the founder (Daniel). Decided under his delegation.

### D18. The overseer: embedded, sidecar, agents, adjudicator

- **Decision:**
  - **Embedded in v1:** the overseer core is embedded in the service process, connected through
    `EPINOIC_OVERSEER_PORT=epinoic_overseer.port`.
  - **Sidecar:** a sidecar replaces it only after passing `integration/overseer-port/CONFORMANCE.md` on every vector,
    the simulation corpus and the tampering cases T1 to T22, with identical results. It is published first on
    `subproject/overseer` (D20) and enabled by a new kit tag.
  - **Overseer agents:** they run asynchronously after delivery and are advisory.
    - Staging: `EPINOIC_OVERSEER_AGENTS=async`, capped at 25 reviews a day, on the asynchronous-work key
      `EPINOIC_ASYNC_ANTHROPIC_API_KEY` (D14). With that cap at 0 or that key missing, the agents are disabled at
      start-up (`async_work_disabled`) and deliveries run unchanged; the service never refuses to start for it.
    - Production: `off` until Bruno's production go.
    - The one exception is the measured M3 fallback (D17).
  - **The simulation's model adjudicator** can no longer clear a formal error in integrated runs. Agents change A5 adds
    `--adjudicator advisory` as the default for integrated runs.
- **Why:**
  - The overseer is a separate sub-project reached only through the overseer port (PROTOCOL.md section 6), under its
    trust rules.
  - "Agent self-reports are advisory; the Overseer trusts only signed engine results" (the translator repository's
    safety rules). The simulation's model adjudicator can currently clear a formal error (agents repository, inspected
    17 October), and an adjudicator that removes a blocker breaks that rule.
  - Async agents on staging produce the data that the D17 and D22 measurements need, within a cap.
- **What the kit changes:**
  - Settings defaults stay (`off`). The staging value is recorded in `deploy/container/README.md`.
  - `agents/PATCH-PLAN.md` A5 states the flag and its default.
  - `DECISIONS.md` marks D18 decided.
- **Who acts, when:**
  - The programme connects the embedded adapter (phase 2).
  - At the last task, Daniel sets `EPINOIC_OVERSEER_AGENTS=async` on the staging host and gives his go for agents
    changes A1 to A5 on a branch of the agents repository.
- **How to reverse:** set `EPINOIC_OVERSEER_AGENTS=off`. Deliveries do not change, because the agents never gate them in
  v1.
- **Authority:** the kit named the founder and Daniel. Decided under his delegation.

### D19. Twofold modes

- **Decision:**
  - **Single mode only** on the website in M2. No website route uses duplicate mode, which costs twice as much.
    Duplicate and combined modes are exercised in the simulation and the agents driver.
  - **Combined mode** comes to the website only in M3, and only when all of these hold:
    - it starts above the router, after `clarify/mixed_request` and the student's explicit choice of both subjects (no
      routing contract change);
    - W8 adds the contract field and the consent UI;
    - the combinator is connected (D33);
    - the overseer reviews it at the N_FOLD floor: each specialist's answer before combination, then the combinator's
      output with the bounded temporary context;
    - there are no half answers.
- **Why:**
  - The agents repository's router never fans out to two specialists (inspected 17 October), and the v1 website has no
    way to present a disclosed conflict between two answers.
  - Combined answers need two generations and a synthesis, which do not fit 100 s.
  - N_FOLD is Daniel's twofold review, and the floor enforces it (PROTOCOL.md section 7a.4).
- **What the kit changes:** nothing. `capabilities.ports.checks.modes` omits `combined` while
  `EPINOIC_COMBINATOR=none`, and the Worker sends `single` only. `DECISIONS.md` marks D19 decided.
- **Who acts, when:** nobody now. At M3, Bruno designs W8.
- **How to reverse:** not applicable; enabling a mode later is additive.
- **Authority:** the kit named the founder and Bruno. This is the programme's decision of record; Bruno may override it
  for his own repository.

### D20. Repositories and visibility

- **Decision:**
  1. **No new GitHub repositories.**
  2. **Sub-projects:** the overseer, the combinator and the flash router stay sub-project directories of the translator
     development branch. Each verified version is published, by a fast-forward-only subtree split, to `origin` branch
     `subproject/<name>`, for example `subproject/flash-router` (`fcf2381`, already published).
  3. **The kit's base commit:** the overseer rebuild commit, plus `0d28eba` (contract 0.3, the named policies), plus the end-to-end
     fixes (`8a78efe`), the argument-diagnostics commit when it lands, and this pre-build branch. Contract 0.3 or later
     must win the merge.
  4. **Canonical translator remote:** `origin` (the danielhyon98-byte development repository) carries the annotated tag
     `integration-kit-v1` and `INTEGRATION_KIT.md` on its default branch. The mirror gets no pointer: its default
     branch is never touched, and it only receives the publishers' `verified-updates`.
  5. **Canonical agents repository:** the public connector (runtime v0.1.0). Website PR #24's vendored v0.2.0 is accepted
     through the v2 pair. Agents changes A1 to A5 go on a branch of the agents repository, never a new repository. A2
     holds only envelope code and synthetic vectors, no translator code or prompt text.
  6. **Visibility:** the translator development repository becomes **private**, consistent with its LICENSE. Only after
     that may the `W*.patch` files and the licensed corpus be published in it. Until then only `apply.mjs`, the
     kit-authored blocks, `ANCHORS.md` and `RESULT.sha256`.
- **Why:**
  - Daniel's latest instruction ("just dont create new repos. just create sub branches") supersedes the 13:25 go-ahead,
    and the attempt at three repositories had been refused anyway.
  - A tag on one remote is what the playbook finds (`PLAYBOOK.md` step 2).
  - The repository is publicly clonable although its LICENSE says it is confidential. The website patch files would
    copy restricted website source into it.
- **What the kit changes:**
  - `integration/README.md` and the combinator and flash-router READMEs replace "separate repository" with the
    `subproject/<name>` branches, and record how to split one.
  - `COMPATIBILITY.json` gains `repositories.translator_visibility` (`public` until changed) and
    `repositories.subproject_branches`.
  - The playbook's step 2 is unchanged.
  - `DECISIONS.md` marks D20 decided, along with D28 and D33's repository form.
- **Who acts, when:**
  - The programme pushes the verified `subproject/*` branches to `origin` (Daniel's 17 October instruction).
  - At the last task, Daniel makes the development repository private. Then Daniel pushes the kit tag and commits the
    pointer.
- **How to reverse:** a published tag is never moved; a corrected kit gets a new tag. Visibility can be changed back by
  Daniel, and patch files are then removed under a new tag.
- **Authority:** the kit named Daniel, with Bruno for the website files. Decided under Daniel's delegation; Bruno may
  override the publication of website-derived files.

### D21. `verified` as the only hosted path to real answers

- **Decision:** On staging and production, no backend other than `verified` may serve a real specialist answer. On
  base P, the pilot entry cannot be combined with a live provider without verification. The mock stays local and
  Access-protected-staging only, under its existing gates.
- **Why:** Daniel's rule: "Z3 is not optional". A specialist backend without checks would be a silent path around the
  required review (website `AGENTS.md`).
- **What the kit changes:**
  - Nothing pins this yet. The kit's `website/tests-website/verify-release.test.js` (W4, base M) has three tests: every
    var block has the checks service off and carries no token; the verified backend needs owned state and runs only on
    loopback development or protected staging; a non-https URL outside loopback, or a missing mode, is a configuration
    problem. None pins "no other backend serves a real specialist answer", and base P has no tested patch set
    (`COMPATIBILITY.json` `website_bases.P`: "not built").
  - Patch set P, when the programme builds it, must add these release tests:
    1. on staging and production, `CHAT_BACKEND` is one of `none`, `mock` and `verified`, and no wrangler environment
       selects `history-pilot` or any other specialist backend;
    2. in `handleChat`, the pilot orchestrator is reachable only wrapped by `withVerification` whenever its provider
       transport is live, and a live transport without the wrapper is refused before admission;
    3. production stays `CHAT_BACKEND=none` (the existing pin, kept unchanged).
  - The M2 activation (owner step 13) sets staging `TRANSLATOR_MODE=http`, which breaks the kit test "every var block
    has the checks service off" by design, just as it changes the staging `CHAT_BACKEND === "mock"` pin. The programme
    prepares that pull request with patch set P, and it replaces the test on purpose with equivalent guards, so no
    guard is silently dropped:
    - production: `TRANSLATOR_MODE` is `none`, `TRANSLATOR_BASE_URL` is empty and `CHAT_BACKEND` is `none`;
    - development: unchanged (`TRANSLATOR_MODE` `none`, empty URL, `CHAT_BACKEND` `mock`);
    - staging: `TRANSLATOR_MODE` is `http` only together with `CHAT_BACKEND` `verified` and an `https://`
      `TRANSLATOR_BASE_URL` that is not loopback; any other staging value of `TRANSLATOR_MODE` is `none` with an empty
      URL;
    - no var block carries a token (unchanged), and `MODES` stays `["none", "http", "binding"]`.
  - `DECISIONS.md` marks D21 "decided; pins pending in patch set P".
- **Who acts, when:** the programme writes the pins into patch set P. At the last task, Bruno merges them with patch set
  P.
- **How to reverse:** a reviewed website pull request that removes the pin. Under this record, that pull request would
  also make Z3 optional, which the programme does not decide.
- **Authority:** the kit named the founder (Daniel). Decided under his delegation; Bruno may override it for his own
  repository.

### D22. Overseer-agent findings after delivery

- **Decision:**
  - **Records:** every asynchronous review result is recorded by the service as metadata only: the verdict id, the plan
    origin, the codes, and the counts by decision, KIT-DL reason and OVS-AGENT kind. No content.
  - **Weekly summary:** written to the service's log store. It covers refusal rates, the false-refusal suspects (row 4
    with W110/W111), unresolved accusations such as `translation_unfaithful`, dropped reviews, any
    `async_work_disabled` start-up notice, the date a provider hard limit was reached and the refusals counted from then
    (D14), and the verdict counts by decision and summary that the production go compares with the Worker's
    `chat_check` events (After M2). Counts only, from metadata. Daniel reads it as the service operator.
  - Nothing ever retracts a delivered answer automatically, and students are not notified in v1.
  - **No per-item human review queue in v1:** no reviewer role exists, and the service retains no content (D15). It is
    revisited at Bruno's production go.
- **Why:** Agent verdicts are advisory (PROTOCOL.md section 6). A confirmed accusation is already held by a deterministic check.
  The summary feeds the D3, D6 and D17 measurements without retaining student text.
- **What the kit changes:**
  - The service adds a metadata-only `review_result` log event and a weekly summary command, `python -m
    epinoic_logic.integration summary --week`, which reads the logs and prints counts only.
  - `DECISIONS.md` marks D22 decided.
- **Who acts, when:** nobody: the kit implements it. Daniel reads the summary weekly once staging runs.
- **How to reverse:** not applicable; adding a queue later is additive.
- **Authority:** the kit named the founder (Daniel). Decided under his delegation.

### D23. Model identifiers

- **Decision:**
  - **Approved:** the `policy.defaultPrimary` entry of `agents/model-assignment.json`, assignment version 2026-10-13.1
    (agents commit `5b60229`), the cheapest tier, for every deployed role: the History specialist, cheapest-tier
    translation, the fidelity reviewer, the combinator and the overseer agents. Its identifier is pinned exactly, as
    that entry's status requires.
  - **Not approved for runtime:** the `policy.defaultComparison` entry, whose identifier status is "UNVERIFIED".
  - **No automatic runtime fallback** (the file's `fallbackRule`).
  - **Switching** follows that file's `switchRule`: a reviewed comparison, recorded next to the change.
  - The flash router names no model, and its plans are refused if they do (KIT-RT-009).
- **Why:**
  - Daniel's rule: every deployed agent runs on the cheapest tier, and the strongest tier only judges, fixes and
    verifies.
  - The assignment file is a proposal, and the translation provider is untested live (both inspected 17 October).
    Pinning the exact identifier avoids alias drift.
- **What the kit changes:**
  - Model identifiers stay configuration only: `EPINOIC_ANTHROPIC_MODEL` on the service host, and website task 03's
    configuration for the specialist.
  - `readiness/check.py --live` reports whether a model is configured (a name check, never a value) and that the
    assignment version is 2026-10-13.1.
  - `DECISIONS.md` marks D23 decided and names the entry, never the identifier.
- **Who acts, when:** at the last task:
  - Daniel sets `EPINOIC_TRANSLATION_PROVIDER=anthropic` and `EPINOIC_ANTHROPIC_MODEL` to the approved entry's
    identifier on the staging service host; it applies to both service keys, `EPINOIC_ANTHROPIC_API_KEY` and
    `EPINOIC_ASYNC_ANTHROPIC_API_KEY` (D14).
  - Bruno sets the specialist's model configuration in website task 03.
- **How to reverse:** unset the model variable. The service then refuses to start live (KIT-HS-009). A switch follows
  the `switchRule`.
- **Authority:** the kit named Bruno (website task 03) and the founder. This is the programme's decision of record; Bruno
  may override it for his own repository.

### D24. Conversation context for follow-ups

- **Decision:** Website 01 decides `priorTurns` and its storage under KEEP and hard delete. The kit never sends prior
  turns to the verification service: `task.user_text` is the current message only. A follow-up claim that depends on
  earlier context is checked as written, which may make it NOT_ELIGIBLE or UNSUPPORTED (labelled as such).
- **Why:** data minimisation (D15). The specialist runtime receives `priorTurns` from the website and is
  unaffected.
- **What the kit changes:** a new test, `tests/verify-orchestrator.test.js`, asserts that a turn with prior turns sends
  a `turn-check` whose `user_text` equals the current message and which contains no prior-turn text. `DECISIONS.md`
  marks D24 decided.
- **Who acts, when:** Bruno, within website 01; no kit action.
- **How to reverse:** a protocol minor version adding an optional context digest. Text would still never be sent
  without a new D15 decision.
- **Authority:** the kit named Bruno. This is the programme's decision of record; Bruno may override it for his own
  repository.

### D25. Timing of a verified turn on base P

- **Decision:** Option (b), a longer synchronous deadline, for M2 staging:
  - `deadlineAt` is **100 s** from the request's receipt;
  - specialist provider timeout `min(20 s, deadlineAt − now − 5 s)`, the pilot's rule, unchanged;
  - the service's checks budget, computed at the checks call as the kit's `with-verification.js` does:
    `budget_ms = min(65 000, deadlineAt − now − checks_tail_ms 5 000 − completion_reserve_ms 2 000)`, and refused
    (`verifier_timeout`, 503 `checks_incomplete`) below `checks_min_ms` 3 000;
  - the Worker's checks timer `budget_ms + checks_tail_ms`;
  - settle margin = `checks_tail_ms` 5 s; completion reserve 2 s.

  The invariant holds (20 + 3 + 5 + 2 = 30 ≤ 100). The worst case is exactly 100 s (3 + 5 + 20 + 65 + 5 + 2, section B),
  and any slip before the checks call shortens the budget, never the reserve, so completion never passes `deadlineAt`.
  For base M the same code gives `min(65 000, deadlineAt − now − 15 000 − 2 000)` and a timer of budget + 15 000. After a client
  disconnect, a turn that outlives the 30 s `waitUntil` window ends `lease_expired`. Base P answers that with the final
  `answer_failed`: the answer is lost, never charged twice and never mislabelled. If the pilot keeps 25 s, the verified
  backend keeps refusing with `KIT-HS-016`, as now. Option (a) is rejected because 6 s of checks would withhold most
  answers with eligible claims. Option (d) is rejected because it releases before the required checks finish. Option
  (c) is M3 (D16).
- **Why:**
  - The timing invariant and the clocks of section B.
  - The pilot's 25 s draft comes from the 30 s `waitUntil` window.
  - The page waits 190 s, so 100 s is well inside it.
  - The service's own `checks_max_ms` is 65 s, so a longer deadline would buy nothing synchronous.
- **What the kit changes:**
  - `COMPATIBILITY.json` `timing.bases.P` becomes
    `{"deadline_ms": 100000, "specialist_ceiling_ms": 20000, "checks_tail_ms": 5000}`, replacing a `deadline_ms` of
    25,000. `timing.completion_reserve_ms` stays 2,000 and base M stays as built.
  - `vectors/handshake/base-p-timing.json` becomes feasible at 100 s, and a new vector keeps 25 s → `KIT-HS-016`.
  - `compat.py` and `compat.js` are regenerated.
  - `website/PATCH-PLAN.md` (patch set P) names the pilot constant to change.
  - `DECISIONS.md` marks D25 decided.
- **Who acts, when:** at the last task, Bruno sets the pilot deadline to 100 s in the reviewed patch-set-P pull request.
- **How to reverse:** Bruno restores 25 s. The verified backend then refuses with `KIT-HS-016` and never shortens the
  checks.
- **Authority:** the kit named Bruno with the founder. This is the programme's decision of record; Bruno may override it
  for his own repository.

### D26. Retry semantics after the specialist call

- **Decision:**
  - **Final refusals:** every refusal after the specialist call has been sent is final. There is no re-arm, so nothing
    is paid twice, and an unchanged resend answers the same code.
  - **Pre-send codes re-arm:** `kit_hs_*`, `specialist_unmapped` and `specialist_unavailable`, through `REARM_CODES`
    on base P.
  - **Public codes:**

    | Code | Status | Copy |
    |---|---|---|
    | `review_unresolved` | 422, not retryable | "This answer didn't pass its automatic checks, so it isn't shown. Ask again in a new conversation." |
    | `checks_incomplete` | 503, not retryable | "This answer's automatic checks couldn't be completed, so it isn't shown. Ask again in a new conversation." |
- **Why:**
  - Base P's rule: once a provider request has been sent, or may have been, every error is final.
  - Withheld text is never stored, so the same answer cannot be re-checked.
  - The copy tells the truth, and says what the student can do.
- **What the kit changes:** nothing. This is already in the blocks (`09-w1-errors.block`, `10-w1-error-copy.block`) and
  in the codes table. `DECISIONS.md` marks D26 decided.
- **Who acts, when:** at the last task, Bruno merges it with patch set P.
- **How to reverse:** a website change making these codes re-armable at the cost of a second generation. It would need
  a D14 budget for that.
- **Authority:** the kit named Bruno. This is the programme's decision of record; Bruno may override it for his own
  repository.

### D27. The review value and its badge

- **Decision:**
  - **Review value:** `checks:integration.v1`, append-only in `REVIEW_STATES`.
  - **Badge**, which follows `checksSummary` (the kit's conservative copy):

    | Summary | Badge |
    |---|---|
    | `formally_checked` | "Automatic checks passed", success tone; on a simulated answer "Automatic checks passed (simulated)", no success tone (D13) |
    | `partly_checked` | "Partly checked", no success tone |
    | `formal_only` | "Partly checked (encoding only)", no success tone |
    | `not_formally_checkable`, or any unknown summary | "Not formally checked" |
    | `incomplete` (development and `sim` only) | "Some checks unavailable" |

  - **Supporting claims in the summary:** `formally_checked` needs every eligible claim of the answer, material or
    supporting, to be positive with its release permitted. When every material eligible claim is, but an eligible
    supporting claim is not (UNKNOWN, TIMEOUT, NOT_ATTEMPTED, a negative result, or positive without permission), the
    summary is `partly_checked`. Supporting claims still never block or withhold (rows 4 and 5 are unchanged).
    Option (a), a "main claims passed" badge over the material-only count, was rejected: it would still put the
    success tone on an answer one of whose own checks returned a counterexample.

  - **M3 fallback:** reserved review value `selected:integration.v1` with the badge "Not formally checked — selected by
    automated reviewers", no success tone, never "passed".
  - The verified backend never produces `passed` or `not_required`.
- **Why:**
  - Base P's convention of naming what ran (its `REVIEW_STATES` gains `checks:history-gate/0.3.0`).
  - "Passed" may appear only when every material eligible claim is positive with its release permitted (PROTOCOL.md
    section 9, condition 13, as built); this record extends that condition to eligible supporting claims. The counts cover material claims only (vectors `row5-supporting-claim-does-not-count`
    and `deliver-with-supporting-blocking-claim`), so without the supporting-claim rule, once D6 is `on`, an answer
    with a supporting COUNTEREXAMPLE would show "Automatic checks passed" in the success tone: a non-success shown as
    success.
  - A fallback answer must be distinguishable from a checked one (D17).
- **What the kit changes:**
  - Before the first kit tag (no stored verdict carries an earlier meaning, D3): the verdict's closed `counts` object
    gains `supporting_eligible` and `supporting_permitted`; `delivery.summarize` and the Worker's
    `decision-table.js` and `release-gate.js` return `formally_checked` only when `permitted == eligible` and
    `supporting_permitted == supporting_eligible`, and otherwise `partly_checked` when `permitted > 0`; the property
    test "a non-definitive status never yields `formally_checked`" extends to supporting claims. `PROTOCOL.md`
    sections 8 and 9 (condition 13), the schemas, `compat.py`, `compat.js` and the MANIFEST are regenerated.
  - New decision vectors: `summary-supporting-unknown-partly-checked.json` and
    `summary-supporting-counterexample-partly-checked.json` (material claims positive and permitted; decision
    `deliver`; summary `partly_checked`); the two existing supporting-claim vectors keep their expected `deliver` and
    `formal_only` and gain the two new counts.
  - Badge vectors in `chat-contract/labels.json` for both supporting-claim cases ("Partly checked", no success tone)
    and for a simulated `formally_checked` answer (D13).
  - `selected:integration.v1` and its badge are added to the reserved vectors (`chat-contract/labels.json`), unused
    until protocol 1.1.
  - `checksBadge` in the W1 review-states block drops the success tone with the " (simulated)" suffix (D13); the other
    blocks stay as they are.
  - `DECISIONS.md` marks D27 decided.
- **Who acts, when:** at the last task, Bruno merges it with patch set P.
- **How to reverse:** copy changes by Bruno. A review value is never removed once rows carry it (rollback rule: keep
  the reader W1).
- **Authority:** the kit named Bruno. This is the programme's decision of record; Bruno may override it for his own
  repository.

---

## Appendix: decisions D28 to D33, added by the built kit

The pre-build's `integration/DECISIONS.md` added six decisions. They fall under the same delegation and are decided
here briefly, in the same form.

### D28. The flash router as a separate sub-agent

- **Decision:**
  - **Repository form:** a sub-project directory on the development branch, published to `subproject/flash-router`
    (D20). It is maintained and released by Daniel under its own version and identity.
  - **Hosted environments:** not attached in M2 (`EPINOIC_FLASH_ROUTER=none`); the floor plan runs.
  - **Attachment later:** only on the hosted Linux non-root image, where the process boundary holds (KIT-RT-016
    otherwise), after the overseer agents' data shows a need.
  - The translator's suite keeps running the router's own suite while it lives in the tree.
- **Why:** The router is advisory and never required (PROTOCOL.md section 7a). Detaching it costs no oversight, because the floor is
  enforced.
- **What the kit changes:** documentation only (the README and DECISIONS mention the sub-branch).
- **Who acts, when:** nobody beyond the programme's sub-branch publishing.
- **How to reverse:** set the variable to the module.

### D29. The minimum-oversight floor

- **Decision:**
  - `minimum-oversight-floor/1` stays as it is now.
  - `minimum-oversight-floor/2` is adopted when the argument diagnostics are connected in phase 2. It adds two agreement
    signals that call for 2 reviews: an error-level named diagnostic, and an unverified dependency.
  - The new floor has its own digest and its own vectors. A floor is only ever raised.
- **Why:** Risk signals only escalate. Diagnostics name exactly the leaps and gaps that a single review misses.
- **What the kit changes:** `FLOOR_RULES/2`, its digest and its vectors, in phase 2.
- **Who acts, when:** nobody: the kit implements it.
- **How to reverse:** pin floor/1 under a new kit tag.

### D30. Overseer-agent profiles

- **Decision:** `standard` only. `fast` is not offered.
- **Why:** The flash pilot named more faults with `fast` (15 of 37 against 11 of 37), but made 10 false accusations
  against 3. It was not adopted, and no optimisation work is done now.
- **What the kit changes:** the overseer hello lists `["standard"]`.
- **Who acts, when:** nobody.
- **How to reverse:** a measured profile adopted under a new kit tag.

### D31. Task type

- **Decision:** `short_answer` until the website carries a task type. Bruno may add a closed field later.
- **Why:** The website sends none (pre-build), and `check_answer.py` uses `short_answer`.
- **What the kit changes:** nothing.
- **Who acts, when:** nobody.
- **How to reverse:** a protocol minor version.

### D32. Live provider timeout

- **Decision:** 20 s per cheapest-tier call (`runtime.PROVIDER_TIMEOUT_S`), always bounded by the budget left.
- **Why:** Two parallel rounds of 4 calls fit the 65 s budget. The provider is unmeasured live.
- **What the kit changes:** nothing.
- **Who acts, when:** nobody.
- **How to reverse:** a measured value under a new kit tag. Thresholds are never relaxed after a measurement; a miss is
  reported.

### D33. The combinator as a separate agent

- **Decision:**
  - **Repository form:** a sub-project directory published to `subproject/combinator` once its pre-build verification
    is clean (D20).
  - **Hosted environments:** not connected in M1 or M2 (`EPINOIC_COMBINATOR=none`, so `combined` is not offered).
  - **When connected (M3, D19):** it runs in its own process. That process receives only the cheapest-tier provider
    credential, `EPINOIC_ANTHROPIC_API_KEY` passed explicitly (the delivery path's key and caps, D14), and the model
    configuration (D23): no signing key, verdict key, overseer secret or service token.
  - The translator never imports it, and the hub decides every synthesis.
  - The translator's suite keeps running its suite.
- **Why:** PROTOCOL.md section 7. It follows the router's fault-boundary pattern.
- **What the kit changes:** the M3 process launcher, documented now and built at M3.
- **Who acts, when:** nobody now.
- **How to reverse:** set the variable to `none`.

---

## Owner actions, in M2 order

No action below has happened. Each happens only at the programme's last task (the website integration), with the named
owner's own go, in this order.

**Programme, before the last task (Daniel's repository, already authorized by his instructions):** implement the kit
changes above in phase 2's protocol step. This includes the kit's base commit, with contract 0.3 or later winning the
merge (D20), and patch set P with the D21 pins. Then publish the verified `subproject/*` branches (D20).

1. **Daniel:** make the translator development repository private (D20, D15).
2. **Daniel:** publish the kit: the annotated tag `integration-kit-v1` on the kit commit, pushed to `origin` only, plus
   `INTEGRATION_KIT.md` and the one-line README pointer on `origin`'s default branch (D20).
3. **Daniel:** give his go for agents changes A1 to A5 on a branch of the agents repository, with `--adjudicator advisory`
   as the integrated default (D18, D20).
4. **Bruno:** merge W0, a docs-only pull request of its own, on the website's `main`, recording "Z3 is required" and
   lifting G0 (D1). This redeploys staging with the mock unchanged.
5. **Bruno:** review and merge PR S (#17): the staging `CHAT_DB` binding, `CHAT_STATE=d1`, and the migrations applied by
   the reviewed staging workflow.
6. **Bruno:** merge base P (#21 to #24): provider transports, the generation budget and the History pilot.
7. **Bruno:** set the pilot deadline to 100 s from receipt (D25). It goes into the patch-set-P pull request of step 11.
8. **Daniel:** choose the container host under the D7 hosting ceiling (USD 30 a month, a fixed-price plan or a
   host-side spending cap, else a billing alert at that amount); this is his own spend decision and the programme's
   only cost before step 12. Build and configure the staging verification service (D7, D12), with at least 3 GiB of
   memory and 2 vCPU; do not start it yet. Build the image from the kit tag, to run as the non-root user. Set, by
   name, in the host's secret store:
   - `EPINOIC_PROFILE=integration`, `EPINOIC_SERVICE_ENV=staging`;
   - `EPINOIC_SERVICE_TOKEN`;
   - `EPINOIC_SIGNING_KEY` / `_ID`, `EPINOIC_VERDICT_KEY` / `_ID`, `EPINOIC_OVERSEER_SECRET` (three distinct keys of
     32 bytes or more);
   - `EPINOIC_OVERSEER_AGENTS=async`, `EPINOIC_FLASH_ROUTER=none`, `EPINOIC_COMBINATOR=none`,
     `EPINOIC_FIDELITY_REVIEW=shadow`;
   Leave every D14 service cap at its default 0 and set neither provider key (`EPINOIC_ANTHROPIC_API_KEY`,
   `EPINOIC_ASYNC_ANTHROPIC_API_KEY`), nor the SDK's default key variable: no live calls. By design the service
   refuses to start until step 12 (`KIT-HS-009`, since staging requires a live provider with its named key, and then
   `KIT-HS-018` while a delivery-path cap is 0), so steps 9 to 11 are not smoke-tested against it; their own tests run
   against the kit's fakes. The two asynchronous modes set here never cause a refusal: while their caps are 0 or their
   key is missing they are disabled at start-up (`async_work_disabled`), and deliveries are unaffected (D14).
9. **Bruno:** set `TRANSLATOR_SERVICE_TOKEN` on the staging Worker with `wrangler secret put` (D7). This deploys a new
   version.
10. **Bruno:** approve the D14 website caps and the `checks` reservation kind (W5), and the D23 specialist model
    configuration (website task 03). Set the USD 25 a month hard limit on the new staging specialist key.
11. **Bruno:** review and merge patch set P, including:
    - the D13 copy, the D21 pins and the D26/D27 codes and values;
    - the 100 s deadline;
    - W5 as a `checks` reservation kind, with a migration at the next free number only if base P's schema constrains
      reservation kinds (D14), applied to staging only by the reviewed workflow step.
12. **Daniel:** enable live calls on the staging service (D14, D15, D23), the owner's enabling from the fail-closed 0:
    1. accept the provider's data terms for two new keys, the verification key and the asynchronous-work key;
    2. set their hard limits, USD 20 and USD 5 a month;
    3. set both keys by name in the host's secret store, the verification key as `EPINOIC_ANTHROPIC_API_KEY` and the
       asynchronous-work key as `EPINOIC_ASYNC_ANTHROPIC_API_KEY` (never the SDK's default variable), then
       `EPINOIC_TRANSLATION_PROVIDER=anthropic` and `EPINOIC_ANTHROPIC_MODEL` to the `policy.defaultPrimary` entry's
       identifier;
    4. set `EPINOIC_PROVIDER_CALLS_PER_DAY=2000`, `EPINOIC_INPUT_TOKENS_PER_DAY=20000000`,
       `EPINOIC_OUTPUT_TOKENS_PER_DAY=2000000`, `EPINOIC_OVERSEER_REVIEWS_PER_DAY=25` and
       `EPINOIC_FIDELITY_REVIEWS_PER_DAY=200`;
    5. start the service; its preflight passes only now. Run `readiness/check.py --live` (its owner rows show both key
       settings and the five caps as set, names only) and confirm that no `async_work_disabled` notice was logged, then
       run the handshake from the staging Worker's side before step 13.
13. **Bruno:** review and merge the pull request that sets staging `CHAT_BACKEND=verified`, `TRANSLATOR_MODE=http` and
    `TRANSLATOR_BASE_URL`. It changes the pinned staging `CHAT_BACKEND === "mock"` assertion on purpose, and replaces
    the kit test "every var block has the checks service off" with the equivalent guards listed in D21 (staging `http`
    only with `verified` and an `https` URL, no token in any var block, production `none`), so no guard is silently
    dropped. Merging it deploys staging. It is the M2 activation.

**After M2: not part of M2, each with its owner's go.**
- **Daniel:** fidelity review `on` on staging, after the measurement (a 95% Wilson lower bound of at least 0.98) and
  a new kit tag (D6).
- **Bruno:** the M3 website design (W9 asynchronous delivery; W8 combined mode). **Programme:** protocol 1.1 (D16, D19).
- **Daniel:** the overseer-selected fallback on staging, after its measurement and a new kit tag (D17).
- **Bruno:** the Container binding target, with the staging-keys pin change (D7).
- **Bruno:** the production go. It needs M2 evidence: at least 200 verified turns; zero label-check violations, meaning
  (a) the delivery rule's condition 13 checks (PROTOCOL.md section 9) and the disclosure and label vectors
  (`tests-website/verify-disclosure.test.js`, `vectors/chat-contract/labels.json`) pass on the deployed staging commit,
  (b) no staging `chat_check` event records a Worker refusal for a re-derivation or label mismatch, and (c) the
  delivered answers' counts by summary in the `chat_check` events equal the D22 summary's verdict counts for the same
  weeks; and measured latency and refusal rates in the D22 summary. It also needs the student-data terms recorded
  (D15) and production caps decided. No production key or call exists before then.
