# Z3 deployment package: the checker on top of the retrained History specialist

Written 23 October 2026 for Daniel, to hand to **a new Claude Code session**. Four files:

| File | What it is |
|---|---|
| `README.md` (this file) | what the package is, the state of every part, how the parts fit, known defects, placeholders, links |
| [`START-PROMPT.md`](START-PROMPT.md) | the exact text Daniel pastes into the new session (he attaches all four files) |
| [`OWNER-ACTIONS.md`](OWNER-ACTIONS.md) | the owner actions still open, in order, each with its owner, the gate it unblocks and the evidence that it happened |
| [`PINS.json`](PINS.json) | repositories by role, the kit commit, the agents pins and the dated values observed on 23 October |

## 1. What this package is, and what it is not

**It is** the instructions and pins that let a new Claude Code session follow the kit's playbook
(`integration/PLAYBOOK.md`) at **one kit commit**, to put the Z3 checker on top of the retrained History specialist on
the website:

- **now**, as a **rehearsal** of the unpublished kit commit `@@KIT_COMMIT@@` (mode REHEARSAL);
- **later**, as an **integration** of the published kit, only after Daniel has tagged it (mode INTEGRATE, decision D20).

**It is not:**

- a deployment: nothing in it has been deployed, hosted, configured or activated;
- an authorization: it authorizes no edit, push, merge, tag, deploy, migration, secret or paid call in any repository.
  Each owner action needs that owner's own go-ahead, in the session, in their own words (`OWNER-ACTIONS.md`);
- evidence of live operation: every result below is a test, a simulation, an inspection or a document's claim. No
  provider was called and no hosted system was used;
- a substitute for the repositories' own rules (`CLAUDE.md`, `AGENTS.md`), which take precedence.

Results of the Z3 checker prove properties of the logic encoding only, never that a claim is true.

## 2. Status, per component

Evidence labels: **[reproduced]** a command the preparing workflow ran, with its output; **[inspected]** read at the
named commit; **[reported]** a document's or the programme's own record, not re-checked here; **[not checked]**.
"Deployed" is **no** on every row: no part of the Z3 checker is deployed anywhere.

| Component | Implemented | Tested | Reviewed | Deployed | Evidence, date |
|---|---|---|---|---|---|
| Translator and Z3 engine (IR 1.0, engine 0.4.0, translator 0.4.0, policy 2026.10-v4, contract 0.4, protocol `epinoic.integration.v1`) | yes | full suite on the kit retarget tree: 6,866 passed, 45 deselected, 4 xfailed (strict markers of known defects), 0 failed, with and without the recorded rounds | the end-to-end fixes by an independent verifier; the verified update `3ecb88e` read back | no | [reproduced] 23 Oct; versions [inspected] in `src/epinoic_logic/version.py`; review [reported] in the 18 Oct handoff report |
| Kit, development line, at `@@KIT_COMMIT@@` (the agents retarget: repositories by role, `agents_pins`, `roles.mjs`, step 9a) | yes | integration tests and full suite green; A2 and the A0 suites on archive copies of every pin; simulation wiring identical to its record | two independent lenses (a diff and regression check; a cold-start rehearsal of steps 1 to 14): no high or medium issue; 4 low, three of them about the kit (section 5) and one about the commit base, which the ancestry check covers | no; **not published**: no tag (D20) | [reproduced] 23 Oct on the uncommitted tree that became `@@KIT_COMMIT@@`; the session re-checks at that commit |
| Same kit: what still blocks | G1 "overseer package" BLOCKER marked "(connected in phase 2)"; the service refuses to start with `KIT-HS-007 overseer_unavailable`; on `origin/main`'s export steps 10 to 12 stop at step 10's drift, so no simulation runs there; on an extra export of the tested base `2cd3182`, a real run (no test double) leaves the website and agents paths NOT RUN with the `KIT-HS-007` reason | | | | [reproduced] 23 Oct |
| Kit, organization line: [`integration/z3-pilot-kit`](https://github.com/Epinoic-AI/Epinoic-Logic-Translator/tree/integration/z3-pilot-kit) `404365c`, [PR #2](https://github.com/Epinoic-AI/Epinoic-Logic-Translator/pull/2) into `verified-updates` | yes (Bruno, 18-19 Oct: embedded overseer port, service gateway, `check.py --live`, base-P timing at 100 s, a partial agents retarget, governance amendments) | its own records [not checked] | not reviewed by Daniel; two of its changes weaken an existing gate and are not adopted by the development line | no | [inspected] 23 Oct; PR head and open merge ref [reproduced] by `ls-remote` |
| Overseer rebuild on the STEM translator | **in progress**, staged, not committed | latest measurement (STEM repair 6): suite 6,965 passed; probes 152/152 named; controls 130/130 clean; contained run 13/13 gates, 0 false alarms; 15/15 STEM mutations | latest independent audit: 2 high, 2 medium open | no | [reported] programme state, 23 Oct 19:00 UTC |
| Published overseer prototype `overseer-prototype` `9547fc9` | yes, on the earlier translator; no port adapter | 110/110 tamperings, 0 false alarms; candidates `6adbd64`, `87eaf86` held (235/254 in the contained run, 3 false alarms) | 25 round-3 findings open | no | [reported] 18 Oct report; 23 Oct state |
| Argument diagnostics | **in progress** | verification round 3: corpus 3 high, invariants 2 high, re-run review 1 high, adversarial 13 issues; repair round 3 running | — | no | [reported] 23 Oct 19:00 UTC |
| Delivery rule (four-minute formal budget; overseer-selected fallback above 90 %, else withheld) | **not started**: part of phase 2, which waits for the rebuild commit | — | — | no | [reported] 23 Oct |
| Round 8 | **not started** (phase 2 first); its connector-built specialists answered 16/16 on 17 Oct | — | — | no | [reported] |
| Specialist runtime pin `8ceba43` (`@epinoic/specialist-runtime` 0.2.0, contract `epinoic.specialist-runtime.v0.2.0`, src tree `7c48eac`) on `feature/history-specialist-integration` (tip `937403a`, docs-only after the pin) | yes (agents owner) | archive copy: 154 tests, 153 pass, 1 skipped (needs the knowledge-base commit in an object store), 0 fail; portable; A2 4/4 | Daniel's approval of the deployable pin is open (`OWNER-ACTIONS.md` A3); the website's vendor record calls this src tree "unreviewed: offline tests only" | no | [reproduced] 23 Oct; vendor record [inspected] at `be4137a` |
| Runtime 0.3.0, open draft [PR #2](https://github.com/Epinoic-AI/Epinoic-Agent-Training/pull/2) `46a6707` (`integration/runtime-pilot-fixes`; contract still v0.2.0; src tree `16926ff`) | yes (Bruno) | A2 information run 4/4 | "do not merge before review"; not a pin | no | [reproduced] A2; PR state [reproduced] by the GitHub API, 23 Oct |
| Knowledge bases | v4 baseline `651d71d` on `main`: the History bundle the runtime pin carries (sha256 `a5b8a2da…9240`, 300,563 bytes); retrained packages on `training/overseer-loop` (`80448d7`): proposals, not reviewed by the owner, not pinned | the exporter (`specialist-runtime/tools/export-bundle.mjs`, identical at `8ceba43` and `937403a`) reproduced the pinned bundle's digest and size and refused an unpinned commit; the runtime manifest's knowledge-base entry equals the pin | the retrained packages: none | no | exporter [reproduced] 18 Oct; manifest row [reproduced] 23 Oct; package status [inspected] |
| Routing `f47c964` (`feature/specialist-routing`, contract `epinoic.specialist-routing.v0.1.0`) | yes | 203 tests, 199 pass, 4 skipped (object store), 0 fail; evaluate PASS on 260 items; portable | — | no | [reproduced] 23 Oct. **Accepts runtime v0.1.0 only**: it does not route over the retrained runtime (a REPORTED row; the website path is History only and unrouted) |
| Harness (API connector), pin `5b60229`, tip `f6d9fdc` of `claude/eloquent-euler-1kuwtf` | runtime 0.1.0 and its routing in one tree; A3 and A5 anchored for `5b60229` | A2 4/4 on `5b60229`; the A3/A5 applier finds 16 anchors once on `5b60229` and refuses `f6d9fdc` (as designed); 16/16 anchors counted at `f6d9fdc` (count only, behaviour not re-tested) | — | no | [reproduced] 23 Oct |
| Website `main` [`6c12674`](https://github.com/Epinoic-AI/epinoic-ai-website/commit/6c12674ab1ac1d39f847f416d111c70ed6d56c27) | no Z3 on `main`; G0 (the Z3 deferral) **in force**; base M | patch set M was tested on `2cd3182`; on `6c12674` every anchor is found and `apply.mjs --verify` reports **drift: `wrangler.jsonc`** (exit 3) | — | no Z3 (Bruno's staging itself runs the mock chat with saved history) | [reproduced] 23 Oct; staging [reported] by the website's own documents |
| W0, [PR #26](https://github.com/Epinoic-AI/epinoic-ai-website/pull/26) `4d8a435` (open draft; regenerated from the organization line `404365c`) | Bruno's docs change | both kit lines read its head as G0 **lifted**; it no longer equals this kit's own W0 draft (9 files differ) | Bruno merges | no | [reproduced] 23 Oct |
| History pilot PRs (open drafts by Bruno): [#23](https://github.com/Epinoic-AI/epinoic-ai-website/pull/23) `d6b1d45`, [#24](https://github.com/Epinoic-AI/epinoic-ai-website/pull/24) `f928ad6`, [#25](https://github.com/Epinoic-AI/epinoic-ai-website/pull/25) `a16b85d`, [#27](https://github.com/Epinoic-AI/epinoic-ai-website/pull/27) `7f6a9bc`, [#28](https://github.com/Epinoic-AI/epinoic-ai-website/pull/28) `8f88f31` | base P (a separate pilot Worker); #25, #27 and #28 carry Bruno's own Z3 adapter over the vendored kit modules | vendored identities: #24 runtime `dfb8144` (src tree `7c48eac`); #25 runtime `8ceba43` (src tree `7c48eac`) and kit from `3ecb88e` (integration tree `8cc7e44`); #27 and #28 runtime 0.3.0 `46a6707` (src tree `16926ff`) and kit from `404365c` (tree `a4f74f9`); all knowledge base `651d71d`. Step 9a: #25 runtime PASS, kit tree BLOCKER; #27 and #28 runtime and kit tree BLOCKER | #28 "never merge before release review" | no | [inspected] `vendor/*/SOURCE.json` at each head; the src tree recomputed from the vendored bytes for `be4137a`, #25 and #27 [reproduced] 23 Oct; #23's content [not checked] |
| History staging prototype `be4137a` (`feature/history-staging-release`) | local only, **not on GitHub**; no Z3; vendors runtime `dfb8144` (src tree `7c48eac`) | step 9a runtime PASS | another workflow is editing it | no | [inspected] committed state only, 23 Oct |
| Hosting, secrets, live calls | **none**: no host chosen (D7), no service image built, no secret set by the programme, no provider call, no Worker configured for the checks | — | — | no | [inspected] the kit and website records; nothing claimed |

## 3. How the parts fit

Roles are the keys of `integration/COMPATIBILITY.json` `repositories` (and of `PINS.json`).

1. A student asks a History question on the website (**website**, Bruno's). On base P the pilot Worker
   (`CHAT_BACKEND=history-pilot`) admits the turn and reserves the budget.
2. The retrained History specialist answers: the specialist runtime at the **runtime pin** (`agents`, Daniel's
   retrained repository), vendored into the website, with the v4 History knowledge base. Its History gate checks
   format and policy only, never facts.
3. The website's adapter sends the answer to the checks service: `GET /v1/capabilities` before the reserve, then
   `POST /v1/turns/check` after the History gate and the release rule. The adapter is Bruno's (`src/chat/pilot-checks.js`
   on PRs #25, #27 and #28; #26 is the docs-only W0) over kit modules vendored from **translator_development** (the kit; the kit's own patch set M is
   base-M simulation material).
4. The checks service (the translator's integration profile, a native Python service; Z3 cannot run in a Worker)
   extracts the claims (D8), checks them with the Z3 engine, runs the embedded overseer, and returns a signed
   `TurnVerdict`. Overseer agents are asynchronous and advisory (D18). It runs on a host under D7: none exists.
5. The website binds the verdict to its turn, re-derives the decision, and delivers the answer with its formal-checks
   disclosure, or withholds it. Under D12 as decided the Worker never claims to verify the signature; the organization
   line amends that (owner action A1).

The other roles: **translator** (the organization's translator repository) receives the programme's verified updates
and carries no tag (D20); **agents_harness** (the API connector) is the training and simulation harness: the
simulation's agents path, A1 and A3 to A5's targets, and, from round 8 on, the arena's dummy specialists built from it
with the v4 master prompts and knowledge bases.

**The pilot's own names, by name only** (Bruno's open PRs; values are never read): `CHAT_BACKEND=history-pilot`,
`HISTORY_PILOT_ENABLED`, `HISTORY_PILOT_ANTHROPIC_KEY`, `HISTORY_PILOT_OPENAI_KEY`, `HISTORY_PILOT_SELECTION`,
`HISTORY_PILOT_CHECKS`, `HISTORY_PILOT_CHECKS_REQUIRED`, `HISTORY_PILOT_VALIDATION`; on the pilot Worker
`TRANSLATOR_MODE`, `TRANSLATOR_BASE_URL`, `TRANSLATOR_SERVICE_TOKEN`, and at PR #28 `TRANSLATOR_VERDICT_KEY` /
`TRANSLATOR_VERDICT_KEY_ID` (D12 as amended on the organization line). Bruno's rollback switches (his documents at PR
#28): delete `HISTORY_PILOT_ENABLED` (503 `composition_disabled` at once); a reviewed PR that sets
`HISTORY_PILOT_SELECTION` back to `null`; in an emergency, a rollback of the pilot Worker to the version recorded before
enablement. All are Bruno's actions.

The kit's service names (`EPINOIC_*`) are in `integration/PLAYBOOK.md` step 11b and `OWNER-ACTIONS.md` phase E.

## 4. What the session does with it

It reads the four files, checks the placeholders and the ancestry, then runs the playbook in the mode Daniel wrote in
the prompt, and returns one report. In REHEARSAL today the expected end is "rehearsal of an unpublished commit, blocked
by G1 and G0", with "Integration ready (local): NO" and "Live ready: NO" (`START-PROMPT.md` lists every expected stop).
It makes no change in the website, and in the agents repositories only a local branch on Daniel's go (step 13).

The session is not "the programme". Authorizations that the kit's documents give to the programme (for example the
sentence in `DECISIONS.md` "Owner actions, in M2 order" saying the programme is "already authorized by his
instructions" to implement kit changes and publish `subproject/*` branches) do not apply to it.

## 5. Known kit defects not fixed at `@@KIT_COMMIT@@`

- **ROLLBACK step 1 wording:** `integration/rollback/ROLLBACK.md` says merging deploys staging through "Cloudflare's
  connected build"; it is the website's GitHub Actions staging workflow on every push to `main`.
- **D25 row on this line:** `COMPATIBILITY.json` `timing.bases.P` is still 25 s (specialist ceiling 20 s, checks tail
  5 s), so every base-P handshake refuses `KIT-HS-016`. D25 decided 100 s; the change is listed under "Kit changes the
  decisions require" and made only on the organization line.
- **Base M on a newer `main`:** patch set M is recorded for `2cd3182`; on `6c12674` it drifts in `wrangler.jsonc`.
  Re-recording it is a kit change after Bruno's merges settle, never the session's.
- No patch set or adapter for base P in this kit (`website_bases.P` "not built"); D21's pins and owner step 13 as
  written do not describe Bruno's separate pilot Worker (question B16, `OWNER-ACTIONS.md` A2).
- Low findings of the verification of the uncommitted retarget (the session checks whether each still holds):
  - `readiness/check.py`: the row "simulation runtime copy" reads PASS on an output made with the overseer test double,
    which its sibling row calls "not evidence" (readiness still reads NO). Never count it.
  - `readiness/check-agents.mjs --vendored` compares the identities a website's `SOURCE.json` declares, not a hash of
    the vendored bytes (recomputed tree ids agreed on 23 Oct).
  - Wording from before the retarget in `agents/TESTED.json` `tested_on` and a comment of `sim/website-driver.mjs`.
- Carried from the 18 Oct report: `integration/README.md` names combinator 0.1.0 (the code is 0.1.3); the PROPOSED
  Dockerfile uses an unpinned base image and unpinned dependencies; G-FAULT delivers 12 of 34 fault cases under the
  overseer test double (D3 question).

## 6. Placeholders and their checks

Three values are set when the package is published. Until then they read as a name between two pairs of at-signs, and
the session stops on any of them (`grep -nE '@@[A-Z_]+@@'` over the four files).

Who fills them, and where: the programme fills all three in the copy of this package handed to Daniel, kept outside the
repository, after the kit commit and the publishing commit are already on `origin`'s branch. A committed copy cannot
name its own commit, so any copy of the package committed to a repository keeps the placeholders: a session given
that copy stops at item 0 of the prompt, as intended. The handed-over copy and the committed copy differ only in these
three values.

| Name | Value | Meaning |
|---|---|---|
| KIT_COMMIT | `@@KIT_COMMIT@@` | the development commit whose `integration/` is the kit this package pins |
| SOURCE_COMMIT | `@@SOURCE_COMMIT@@` | the development commit this package was published from |
| SOURCE_BRANCH_SHA | `@@SOURCE_BRANCH_SHA@@` | the tip of `claude/z3-verification-engine-plan-nk3luq` at publication |

Checks: KIT_COMMIT is an ancestor of (or equal to) SOURCE_COMMIT, which is an ancestor of (or equal to)
SOURCE_BRANCH_SHA, which is an ancestor of (or equal to) the branch tip the session fetches; `PINS.json` `agents_pins`
equals `integration/COMPATIBILITY.json` `agents_pins` at KIT_COMMIT. In INTEGRATE mode the tag `integration-kit-v1`
must resolve to KIT_COMMIT. Any difference stops the session.

## 7. Links

- Translator development (role `translator_development`, Daniel's):
  [danielhyon98-byte/https-github.com-lovishchopra-NL2FOL](https://github.com/danielhyon98-byte/https-github.com-lovishchopra-NL2FOL),
  branch [`claude/z3-verification-engine-plan-nk3luq`](https://github.com/danielhyon98-byte/https-github.com-lovishchopra-NL2FOL/tree/claude/z3-verification-engine-plan-nk3luq);
  kit commit [`@@KIT_COMMIT@@`](https://github.com/danielhyon98-byte/https-github.com-lovishchopra-NL2FOL/commit/@@KIT_COMMIT@@);
  package published at [`@@SOURCE_COMMIT@@`](https://github.com/danielhyon98-byte/https-github.com-lovishchopra-NL2FOL/commit/@@SOURCE_COMMIT@@).
- Translator, organization (role `translator`; former path `Bruno-ios/Epinoic-Logic-Translator`, redirected):
  [Epinoic-AI/Epinoic-Logic-Translator](https://github.com/Epinoic-AI/Epinoic-Logic-Translator),
  [`verified-updates`](https://github.com/Epinoic-AI/Epinoic-Logic-Translator/tree/verified-updates),
  [PR #2](https://github.com/Epinoic-AI/Epinoic-Logic-Translator/pull/2).
- Retrained agents (role `agents`, Daniel's):
  [Epinoic-AI/Epinoic-Agent-Training](https://github.com/Epinoic-AI/Epinoic-Agent-Training): runtime pin
  [`8ceba43`](https://github.com/Epinoic-AI/Epinoic-Agent-Training/commit/8ceba43f576b49ea754a8994dbc130a6549a4699),
  knowledge bases [`651d71d`](https://github.com/Epinoic-AI/Epinoic-Agent-Training/commit/651d71ded41d4a3b8a106fe23b4198e7fc292146),
  routing [`f47c964`](https://github.com/Epinoic-AI/Epinoic-Agent-Training/commit/f47c964df6f3a9ad93d3e8ff9a18a442b2820fbd),
  [PR #2](https://github.com/Epinoic-AI/Epinoic-Agent-Training/pull/2) (runtime 0.3.0).
- Harness (role `agents_harness`, Daniel's):
  [danielhyon98-byte/epinoic-agent-training-api-connector](https://github.com/danielhyon98-byte/epinoic-agent-training-api-connector),
  pin [`5b60229`](https://github.com/danielhyon98-byte/epinoic-agent-training-api-connector/commit/5b60229b6f08bea88f7cf28316282469942ce46d).
- Website (role `website`, Bruno's): [Epinoic-AI/epinoic-ai-website](https://github.com/Epinoic-AI/epinoic-ai-website),
  tested base M [`2cd3182`](https://github.com/Epinoic-AI/epinoic-ai-website/commit/2cd318208980e5b236d16b4281dfc0560a7b9610),
  [pull requests](https://github.com/Epinoic-AI/epinoic-ai-website/pulls).
- Z3 source mirror (reference only):
  [danielhyon98-byte/https-github.com-Z3Prover-z3](https://github.com/danielhyon98-byte/https-github.com-Z3Prover-z3).
- The kit at its commit: [`integration/README.md`](https://github.com/danielhyon98-byte/https-github.com-lovishchopra-NL2FOL/blob/@@KIT_COMMIT@@/integration/README.md),
  [`PLAYBOOK.md`](https://github.com/danielhyon98-byte/https-github.com-lovishchopra-NL2FOL/blob/@@KIT_COMMIT@@/integration/PLAYBOOK.md),
  [`DECISIONS.md`](https://github.com/danielhyon98-byte/https-github.com-lovishchopra-NL2FOL/blob/@@KIT_COMMIT@@/integration/DECISIONS.md),
  [`COMPATIBILITY.json`](https://github.com/danielhyon98-byte/https-github.com-lovishchopra-NL2FOL/blob/@@KIT_COMMIT@@/integration/COMPATIBILITY.json).

The website, the retrained agents repository and the organization's translator repository are private or not readable
without access: the links work only for accounts that have it.

## 8. What this supersedes

Section 1 ("Start prompt") of
[`docs/handoff/NEW-SESSION-Z3-WEBSITE-LAUNCH.md`](https://github.com/danielhyon98-byte/https-github.com-lovishchopra-NL2FOL/blob/claude/z3-verification-engine-plan-nk3luq/docs/handoff/NEW-SESSION-Z3-WEBSITE-LAUNCH.md):
its prompt rehearsed `86ab0ba`, whose kit still named the API connector as the agents repository. Use
`START-PROMPT.md` instead. The rest of that document stays background; where its pins differ from `PINS.json`,
`PINS.json` holds.
