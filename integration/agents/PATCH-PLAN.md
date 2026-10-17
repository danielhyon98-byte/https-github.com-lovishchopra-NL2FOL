# Agents change plan (A0 to A5)

**Owner: Daniel.** Work in the agents repository is authorized only by his own messages in the session's
conversation, after decision D20 (playbook step 13), on a new local branch in a worktree under `<scratch>`. The
runtime and the router do not change.

- **A0. `specialist-runtime/` and `specialist-routing/`: no change.** Their suites must keep passing; the counts are
  recorded, never pinned. `claims: null` stays, with its pinning tests.
- **A1. Docs** (prose for the owner to write in that repository): `docs/related-projects/logic-translator-nl2fol.md`
  says Z3 is required on the website path, the layer wraps the runtime result in an outer envelope, `claims` stays
  `null` by design, and names the port `epinoic.integration.specialist-answer.v1`; `README.md` rewords "No Z3, claim
  extraction or formal-check badges": the runtime stays free of Z3 and the required checks run outside it;
  `docs/DEPLOYMENT-READINESS.md` rewords the claims row to "by design".
- **A2. `integration/checks-port/`** (new; **built in the kit at `integration/agents/checks-port/`**): `package.json`;
  `src/envelope.js` (the result's schema and contract, `outcome === "answer"`, the gate passed, `claims: null`, the
  digests; result schema v1 and v2); `test/envelope.test.js` (the repository's own `createOfflineTestRuntime` with the
  synthetic bundle wraps an unchanged frozen result; the digests agree with the cross-repository vector; every
  non-answer outcome is refused); `vectors/` (a copy of the kit's synthetic vector, kept fresh by
  `integration/tools/vectors.py`); its own `check:portable`. Tested on an archive copy of the agents repository at
  `5b60229`: copied to `integration/checks-port/`, `node --test integration/checks-port/test/*.test.js` passes 3 of 3,
  `check:portable` prints "portable", and the runtime's own suite is unchanged (120 of 120).
- **A3. `integration/z3/check_answer.py`**: replace its reads of `hub.channels[...].transmitted_reports` with the
  hub's public view or the verdict; forward the signed reply's id and digest; keep the hard-coded simulation key behind
  an explicit `--simulation` flag (the default) and refuse to run otherwise; optionally `--service URL` to call the
  local checks port for parity. **Connected in phase 2**, when the overseer's public view exists on the translator side.
- **A4. `tools/readiness-check.mjs`**: rows for the kit's compatibility, read from a `KIT_COMPATIBILITY` path; the
  existing blockers stay and the blocker count is never pinned. (The kit's own `integration/readiness/check-agents.mjs`
  reads the same contracts from an archive copy without changing the repository.)
- **A5.** Decision D18: integrated runs treat the simulation's Z3 adjudicator as advisory, so it can no longer remove a
  blocker (a flag and its documentation).
