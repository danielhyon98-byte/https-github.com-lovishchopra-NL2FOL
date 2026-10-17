# Website change plan (W0 to W8) and the kit's patch material

**Owner: Bruno.** Website work is authorized only by a decision Bruno has recorded on the website's published `main`
(gate G0, playbook step 4) together with the user's own request. While G0 is in force the kit's material is applied
only to a disposable export, never to a branch, and W0 exists only as a patch file offered to Bruno.

**Milestones.** M1 (the local simulation) needs W1 to W4 and W6 on base M, applied only to a disposable export unless
G0 is lifted. M2 (a staging pilot) needs base P, patch set P, W5 and the owner actions (hosting D7, secrets, caps D14,
models D23, data terms D15, timing D25). W7 and W8 wait for their decisions. W0 is Bruno's alone.

## What the kit carries for base M (`2cd3182`), and how it was tested

- `src/verify/*.js`: the adapter modules (copied as they are into the website's `src/verify/`);
- `tests/*.test.js`, `tests/kit-vectors.js`: the adapter's own tests (into the website's `tests/`), reading the vectors
  that `apply.mjs` copies into `tests/fixtures/kit/`;
- `tests-website/*.test.js`: tests that need the website itself (contract, handler end to end with the node:sqlite D1,
  configuration pins, disclosure), copied into the website's `tests/`;
- `blocks/M/*.block`: one kit-authored edit per file and anchor, each naming its W-step; `ANCHORS.md` the anchors and
  their counts; `apply.mjs` the applier; `patches/M/BASE`, `RESULT.sha256` (the SHA-256 of every file the patch set
  touches on the pinned base) and `TESTED.json` (where and how it was tested).

Tested on a disposable export of `2cd3182` with Node 22: the baseline is 287 of 290 passing (the 3 failures need the
Playwright devDependency); with the patch set applied, 358 of 361 pass, the same 3 failing and no other, and the 71 new
tests pass; the rollback rehearsal (playbook step 11a) gives steps 1 to 4 PASS and step 5 (base P) NOT RUN. `apply.mjs --verify` on a fresh export prints `exact`. A renamed anchor stops the applier with
`anchor not found: <file>: <anchor>` before anything is written. The `W*.patch` files are not published while the
translator repository is public (decision D20); `apply.mjs` applies the same blocks.

## The steps

- **W0. Docs** (Bruno only; the session writes `<scratch>/report/W0-docs.patch` against `origin/main`, never applied):
  record the decision in `docs/current-state.md` (replacing "Z3 remains deferred." and the "Deferred" bullet) and name
  `epinoic.integration.v1` (G0's positive marker); replace the deferral paragraph of `docs/architecture.md`; mark the
  notices of `docs/drafts/chat-architecture-design.md` and `docs/handoff/04-logic-translator.md` superseded by the
  protocol (kit tag `integration-kit-v1`); replace invariant 25 of `docs/handoff/05-integration-planning-brief.md` §9
  with "Every released answer requires the checks port; integration follows `epinoic.integration.v1`".
- **W1. Contract reader** (additive; ships before any writer; blocks 01 to 17): `REVIEW_STATES` gains
  `"checks:integration.v1"` (append-only); `CHECK_STATUSES`, `FIDELITY_STATES`, `CHECK_SUMMARIES`, `CHECK_LIMITS`
  (12 entries, 200 characters), `SCOPE_STATEMENT` (verbatim) and `checkLabel`; the optional `checks` and
  `checksSummary` in the answer's result and reply fields, validated after the review check (both or neither; present
  exactly with the verified review; closed values; never a negative status); history's `reply()` copies them and its
  `publicTurnCode` reads `src/verify/codes.js` first; `review_unresolved` (422) and `checks_incomplete` (503), both not
  retryable, in `ERRORS` and in the page's `ERROR_COPY`; the page's badge for the verified review follows its
  `checksSummary` (`checksBadge`, decision D27, conservative default: "Automatic checks passed" only for
  `formally_checked`, where every material eligible claim has a permitted positive result; "Partly checked" for
  `partly_checked` and "Partly checked (encoding only)" for `formal_only`, with no success tone; "Not formally checked"
  for `not_formally_checkable`, "Some checks unavailable" for `incomplete`; never "Reviewed"), the checks rendered with
  `textContent` and the scope statement shown once, and `X-Chat-Simulated` read next to `X-Chat-Backend`.
- **W2. Outbound client and readiness** (new files only): `translator-client.js`, `canonical-json.js`, `sha256.js`,
  `compat.js`, `subject-map.js`, `verification.js` (`configProblem()` synchronous; `ready({signal})` with a per-isolate
  60 s cache and an injectable `now()`); tests `verify-client.test.js`, `verify-readiness.test.js`.
- **W3. Decorator and release gate** (blocks 20 to 37): `with-verification.js`, `specialist-port.js`,
  `router-port.js`, `decision-table.js`, `release-gate.js`, `codes.js`, and for the simulation only
  `specialist-orchestrator.js` (it refuses to build without an explicit runtime). In `handler.js`: `chatBackendMode`
  returns `verified` only with `CHAT_BACKEND=verified`, owned state and loopback development or protected staging with
  verified access; `X-Chat-Backend: verified` and `X-Chat-Simulated: 1`; a request naming `X-Mock-Scenario` is refused;
  the orchestrator is `withVerification(options.verified.inner)` and `options.orchestrator` is ignored; the
  configuration check before the store; `verification` passed to the turn. In `turn.js`: `ready()` before routing
  (replays never reach it); `turn`, `deadlineAt` and `stillPending` in the orchestrator's context; a raw body refused;
  error results stored under their kit raw code; the release gate after the existing one; `simulated` from the
  outcome. In `store.js`: `attemptPending`, one owner-scoped statement reusing `SQL.readAttempt`. Tests
  `verify-orchestrator.test.js`, `verify-vectors.test.js`, `verify-handler.test.js`.
- **W4. Configuration and pins** (blocks 40 to 44): `TRANSLATOR_MODE: "none"` and `TRANSLATOR_BASE_URL: ""` in all
  three var blocks of `wrangler.jsonc` (no `CHAT_BACKEND` value changes; the simulation passes `CHAT_BACKEND=verified`
  in the env object it gives `handleRequest`); `TRANSLATOR_SERVICE_TOKEN` named in `.dev.vars.example`; the
  disclosure rewritten under the verified backend with the same fail-closed rule as live routing. Tests
  `verify-release.test.js`, `verify-disclosure.test.js`.
- **W5. Usage and caps** (M2 only, before any real call; not in this kit): the next free migration number, additive,
  pinned in `tests/migrations.test.js` as that file's own comment requires; preferably a `checks` reservation kind in
  base P's `src/budget/` (D14); applied to staging only by the reviewed staging workflow.
- **W6. Logs** (block 28): one `chat_check` line per verified turn, labels only; the existing `chat_request` key-set
  pins stay unchanged.
- **W7. A STEM subject on the website** (decision D9) and **W8. twofold modes on the website** (D19): not in M1.

## Base P (patch set P)

Not built: no base-P website was available at kit build (`COMPATIBILITY.json` `website_bases.P`). It is built only
against a base-P website and marked experimental until base P is merged: `turn.js` already passes `principal`,
`turn` and `deadlineAt`; `REVIEW_STATES` already has three values; `X-Chat-Simulated` already exists; the inner
orchestrator is `createPilotOrchestrator`, which exposes the frozen runtime result as `outcome.specialist` and adds the
kit's pre-send raw codes to `REARM_CODES`; every refusal after the provider request is final; the timing comes from D25.
