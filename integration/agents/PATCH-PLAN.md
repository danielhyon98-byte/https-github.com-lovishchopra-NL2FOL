# Agents change plan (A0 to A5)

**Owner: Daniel.** Work in the agents repositories is authorized only by his own messages in the session's
conversation, after decision D20 (playbook step 13), on a new local branch in a worktree under `<workdir>`; his go
names the repository. The runtime and the router do not change.

**Two repositories, by role** (`COMPATIBILITY.json` `repositories`; the pins are `agents_pins`):

- `repositories.agents`, **the retrained repository**: the specialist runtime the website is to deploy, at the runtime
  pin `8ceba43` (`feature/history-specialist-integration`; package 0.2.0, contract
  `epinoic.specialist-runtime.v0.2.0`), its exporter at the same commit, the knowledge bases at `651d71d` (`main`), and
  the routing at the routing pin `f47c964` (`feature/specialist-routing`). No ref holds both the runtime and the
  routing. Nothing is deployed by the kit.
- `repositories.agents_harness`, **the harness**: the training and simulation harness (runtime 0.1.0 and its routing in
  one tree, `integration/z3/`, `simulation/`, `tools/`) at the harness pin `5b60229` (`claude/eloquent-euler-1kuwtf`),
  the commit A3 and A5's anchors were written for.

The changes, each with its repository and commit:

- **A0. No change, in both repositories:** `specialist-runtime/` (the retrained repository at the runtime pin `8ceba43`;
  the harness at its pin `5b60229`) and `specialist-routing/` (the retrained repository at the routing pin `f47c964`;
  the harness at `5b60229`). Their suites must keep passing; the counts are recorded, never pinned (`TESTED.json`,
  `A2.runs`). `claims: null` stays, with its pinning tests.
- **A1. Docs, in both repositories** (prose for the owner to write there): in the retrained repository, a note in
  `specialist-runtime/README.md` (or a new `docs/related-projects/` file) that names the port
  `epinoic.integration.specialist-answer.v1`, says the layer wraps the runtime result in an outer envelope and that
  `claims` stays `null` by design; in the harness, `docs/related-projects/logic-translator-nl2fol.md` says Z3 is
  required on the website path, the layer wraps the runtime result in an outer envelope, `claims` stays `null` by
  design, and names the port; `README.md` rewords "No Z3, claim extraction or formal-check badges": the runtime stays
  free of Z3 and the required checks run outside it; `docs/DEPLOYMENT-READINESS.md` rewords the claims row to "by
  design".
- **A2. `integration/checks-port/`, in both repositories** (new; **built in the kit at
  `integration/agents/checks-port/`**): in the retrained repository at the runtime pin `8ceba43` (runtime v0.2.0) and
  in the harness at its pin `5b60229` (runtime v0.1.0). `package.json`; `src/envelope.js` (the result's schema and
  contract, `outcome === "answer"`, the gate passed, `claims: null`, the digests; result schema v1 and v2);
  `test/envelope.test.js` (the repository's own `createOfflineTestRuntime` with the synthetic bundle wraps an unchanged
  frozen result; the digests agree with the cross-repository vectors v1 and v2; the turns that end in another outcome,
  in the copy's own callback vocabulary for its runtime contract, are refused; and every outcome the copy's runtime
  declares other than an answer is refused with `KIT-REQ-012`); `vectors/` (copies of the kit's synthetic answer
  vectors, kept fresh by `integration/tools/vectors.py`); its own `check:portable`. Tested on archive copies of both
  pins (`TESTED.json`, `A2`): copied to `integration/checks-port/`, `node --test integration/checks-port/test/*.test.js`
  passes 4 of 4 on each, `check:portable` prints "portable", and each runtime's own suite is unchanged. No anchors: A2
  is new files only.
- **A3. `integration/z3/check_answer.py`, harness only** (the retrained repository has no `integration/z3/`; **built in
  the kit**: replacements `A3-1` to `A3-8` of `patches/agents-A3-A5.json`, anchors for the harness pin `5b60229`,
  applied by `apply-agents.mjs`): the claim texts of its findings come from the reply the hub delivered (its signed
  payload), never from the channel's private `transmitted_reports`; the output forwards that reply's `message_id`,
  `payload_sha256`, `signature_key_id` and whether it is signed (`reply`, null for a REJECTED receipt) and says
  `"simulation": true`; the hard-coded key stays behind the explicit `--simulation` mode, the only mode and the
  default, and any other option is refused (exit 2, `simulation_only`); the hub names the specialist
  `<slug>-specialist`, as the arena and the checks port do, so its credit rules read it. Not built: the optional
  `--service URL` parity call (its input carries no runtime result to wrap; the agents driver of the simulation calls
  the checks port through the specialist port instead), and the overseer's public view (the rebuilt overseer brings it;
  the delivered reply is the hub's own public output until then).
- **A4. `tools/readiness-check.mjs`, harness only** (prose for the owner): rows for the kit's compatibility, read from a
  `KIT_COMPATIBILITY` path; the existing blockers stay and the blocker count is never pinned. (The kit's own
  `integration/readiness/check-agents.mjs` reads the same contracts from archive copies, by role, without changing
  either repository.)
- **A5. Harness only** (anchors for the harness pin `5b60229`). Decision D18 (decided): integrated runs treat the
  simulation's Z3 adjudicator as advisory, so it can no longer remove a blocker (**built in the kit**: replacements
  `A5-1` to `A5-8`). `simulation/workflows/real-agent-training-cycle.js` takes `args.adjudicator`, `advisory` (the
  default) or `authoritative`: in the advisory mode every Z3 error finding blocks whatever the adjudicator ruled, its
  rulings are still recorded and shown, and each round records the mode (`z3Adjudicated.mode`); `authoritative`
  reproduces the runs made before A5. `simulation/tools/report.mjs` takes the same `--adjudicator` (default
  `advisory`) and counts blockers the same way; a report of a run made before A5 is regenerated with `--adjudicator
  authoritative`. The prompts and the specialist's feedback texts are unchanged: whether they should say that a ruled
  artefact still blocks is the training owner's choice (prose, like A1).

**Applying A3 and A5.** `node integration/agents/apply-agents.mjs --target <copy> [--check] [--patch <file>]` writes only
into an archive copy whose `.kit-archive-commit` names `5b60229` (`agents_pins.harness.commit`, the commit the anchors
were written for); every anchor must occur exactly once or nothing is written. On the owner's go (D20: a branch of the
harness), the diff it writes (`--patch`) is applied there with `git apply` and committed by that repository. Tested on
an archive copy of `5b60229` (`TESTED.json`): the anchors, the written diff (`git apply --check`), four check_answer
probes (same statuses, findings and counts; the reply fields added; `--live` refused), the report in both modes, the
runtime suite (120 of 120), the router suite (175 of 175) and the readiness Z3 rows, unchanged.

**A deploying session never re-anchors.** The harness branch moves (on 23 October 2026 its tip was `f6d9fdc`, where
only `simulation/` changed and each of the 16 anchors is still found once: counted, not re-tested). The applier refuses
any commit other than the harness pin, and the deploying session reports that refusal. A re-anchor is a kit change,
made by the programme for the harness commit Daniel names with his go: re-read the changed files against A5's rule
(D18), re-anchor, re-run the probes and the report in both modes, record it in `TESTED.json`, and move
`agents_pins.harness` with it.
