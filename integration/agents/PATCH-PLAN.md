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
- **A3. `integration/z3/check_answer.py`** (**built in the kit**: replacements `A3-1` to `A3-8` of
  `patches/agents-A3-A5.json`, applied by `apply-agents.mjs`): the claim texts of its findings come from the reply the
  hub delivered (its signed payload), never from the channel's private `transmitted_reports`; the output forwards that
  reply's `message_id`, `payload_sha256`, `signature_key_id` and whether it is signed (`reply`, null for a REJECTED
  receipt) and says `"simulation": true`; the hard-coded key stays behind the explicit `--simulation` mode, the only
  mode and the default, and any other option is refused (exit 2, `simulation_only`); the hub names the specialist
  `<slug>-specialist`, as the arena and the checks port do, so its credit rules read it. Not built: the optional
  `--service URL` parity call (its input carries no runtime result to wrap; the agents driver of the simulation calls the
  checks port through the specialist port instead), and the overseer's public view (the rebuilt overseer brings it; the
  delivered reply is the hub's own public output until then).
- **A4. `tools/readiness-check.mjs`**: rows for the kit's compatibility, read from a `KIT_COMPATIBILITY` path; the
  existing blockers stay and the blocker count is never pinned. (The kit's own `integration/readiness/check-agents.mjs`
  reads the same contracts from an archive copy without changing the repository.)
- **A5.** Decision D18 (decided): integrated runs treat the simulation's Z3 adjudicator as advisory, so it can no longer
  remove a blocker (**built in the kit**: replacements `A5-1` to `A5-8`). `simulation/workflows/real-agent-training-cycle.js`
  takes `args.adjudicator`, `advisory` (the default) or `authoritative`: in the advisory mode every Z3 error finding blocks
  whatever the adjudicator ruled, its rulings are still recorded and shown, and each round records the mode
  (`z3Adjudicated.mode`); `authoritative` reproduces the runs made before A5. `simulation/tools/report.mjs` takes the same
  `--adjudicator` (default `advisory`) and counts blockers the same way; a report of a run made before A5 is regenerated
  with `--adjudicator authoritative`. The prompts and the specialist's feedback texts are unchanged: whether they should
  say that a ruled artefact still blocks is the training owner's choice (prose, like A1).

**Applying A3 and A5.** `node integration/agents/apply-agents.mjs --target <copy> [--check] [--patch <file>]` writes only
into an archive copy whose `.kit-archive-commit` names `5b60229` (the commit the anchors were written for); every anchor
must occur exactly once or nothing is written. On the owner's go (D20: a branch of the agents repository), the diff it
writes (`--patch`) is applied there with `git apply` and committed by that repository. Tested on an archive copy of
`5b60229` (`TESTED.json`): the anchors, the written diff (`git apply --check`), four check_answer probes (same statuses,
findings and counts; the reply fields added; `--live` refused), the report in both modes, the runtime suite (120 of 120),
the router suite (175 of 175) and the readiness Z3 rows, unchanged.
