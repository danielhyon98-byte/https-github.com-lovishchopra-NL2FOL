# Owner actions still open, in order

As of 23 October 2026. Taken from the kit's "Owner actions, in M2 order" (`integration/DECISIONS.md` at
`@@KIT_COMMIT@@`) as the agents retarget changed them, and from what Bruno's open pull requests now ask.

**None of these has happened. This package performs none of them**, and neither does the new Claude Code session: it
reports which are still open. Each happens only with its owner's own go-ahead, given by that owner in their own words.
A later phase does not start before the gate it needs is open.

**Deploy triggers (website).** Every push to the website's `main` runs `.github/workflows/staging.yml`, which deploys
that commit to the staging Worker (read at `6c12674`). So every merge Bruno makes below (D1, D2, D3, F1) redeploys
staging, and setting a Worker secret deploys a new version (kit owner step 9). Bruno weighs that before each merge.

**How these map to the kit's numbered owner steps** (`DECISIONS.md`, "Owner actions, in M2 order"):

| Kit step | Here | Note |
|---|---|---|
| 1 (repository private) | B1 | |
| 2 (publish the tag) | B2 | |
| 3a, 3b (agents go-aheads) | C1, C2 | |
| 4 (merge W0) | D1 | |
| 5 (Bruno: review and merge PR S, #17) | **done** | #17 is an ancestor of website `main` `6c12674`; the merge of #29 records "PR S (#17) activated on October 20, 2026" [inspected] |
| 6, 7 (base P, 100 s deadline) | D2 | |
| 8 (host, image, service names) | E1 | |
| 9 (`TRANSLATOR_SERVICE_TOKEN`) | E2 | |
| 10 (website caps, models) | E3 | |
| 11 (patch set P) | D2, D3, under A2 | the kit has no patch set P; Bruno's pilot stack takes its place if Daniel's answer to B16 (A2) accepts it |
| 12 (live calls) | E4 | |
| 13 (activation via `CHAT_BACKEND=verified`) | F1, under A2 | replaced by the pilot activation PR #28 if A2 accepts B16 |
| "Programme, before the last task" | A3, A4, A5 | a programme authorization; it does not extend to the new Claude Code session |

**Ownership** (the programme's record, `DECISIONS.md`): the translator repositories and the agents repositories (both
roles) are **Daniel's**; the website is **Bruno's**. The organization line (`integration/z3-pilot-kit`, PR #2 of
Epinoic-AI/Epinoic-Logic-Translator) records "Bruno's decisions of 18 October 2026" that reassign some of these (Bruno
publishes the kit tag on the organization repository, Bruno reviews agents changes, the host runs on Bruno's account).
Those amendments concern Daniel's repositories and await Daniel's decision in A1; until then the record above holds.

## Phase A. Decide the kit to tag

| # | Owner | Action | Unblocks | Evidence that it happened |
|---|---|---|---|---|
| A1 | Daniel, with Bruno | Reconcile the two kit lines: the development line at `@@KIT_COMMIT@@` and the organization line `404365c` (PR #2). Decide that line's amendments (who tags and where, who authorizes agents changes, the hosting account, caps, its base-P decision Z-D21, D12 as amended so the pilot Worker verifies the signature, the D25 row) and keep no weakened gate: that line turns the routing-contract row into REPORTED when routing is absent and gives the simulation a stand-in router; the development line keeps both as they were | one kit commit to tag | a development commit carrying the reconciled kit, with the union of both lines' test assertions except those encoding a weakened gate; `DECISIONS.md` records each amendment accepted or declined |
| A2 | Daniel | Answer the website's question B16: the separate pilot Worker (`CHAT_BACKEND=history-pilot`, checks required) in place of D21's `verified` path and owner step 13 as written; asynchronous modes off at start | the D21 text and the activation step of the kit to tag | the answer recorded in `DECISIONS.md` (D21) at the kit commit |
| A3 | Daniel | Approve the deployable runtime pin: `8ceba43` (runtime 0.2.0, as tested), or another commit after review (0.3.0 `46a6707` is an open draft PR by Bruno, "do not merge before review"); another pin is re-measured by the programme before the tag | step 9a's vendored-runtime rows; the tag | `agents_pins.runtime` at the kit commit, and Daniel's approval noted in `DECISIONS.md` |
| A4 | Daniel | Keep the v4 knowledge-base baseline `651d71d`, or adopt a retrained package: re-pin the runtime manifest and run the exporter in the retrained repository, then the kit's `agents_pins.knowledge_bases`, then Bruno re-vendors | which knowledge the deployed History specialist carries | the runtime manifest's `source.commit` and `bundleSha256` equal to `agents_pins.knowledge_bases` (step 8's check) |
| A5 | Programme (Daniel's sessions) | Phase 2: merge the rebuilt overseer with its port adapter, the argument diagnostics, the delivery rule, round 8 and its fixes; make the "Kit changes the decisions require" (among them the D25 row, D14 caps and named keys, `readiness/check.py --live`); re-record patch set M on the then-current website `main` if it moved | G1, `KIT-HS-007`, the simulation gates, step 10's drift | `check.py --g1` all PASS; the service starts on loopback; `run_sim.py` gates PASS; `apply.mjs --verify` `exact` on `origin/main` |

## Phase B. Privacy, access and the tag (Daniel)

| # | Owner | Action | Unblocks | Evidence that it happened |
|---|---|---|---|---|
| B1 | Daniel | Make the development repository private (D20, D15; it is public on 23 Oct) and give Bruno read access to the tagged kit, or agree that Bruno re-vendors from the verified update with the same integration tree | the tag | the GitHub API reports `private: true`; Bruno's access or the agreement recorded |
| B2 | Daniel | Publish the kit: the annotated tag `integration-kit-v1` on the kit commit, pushed only to the repository `kit_tag_repository` names (the development repository), plus `INTEGRATION_KIT.md` and the README pointer on its default branch | INTEGRATE mode (playbook step 2); a package republished for that commit | `git cat-file -t integration-kit-v1` prints `tag` and it resolves to `PINS.json` `kit.kit_commit` |

## Phase C. Agents go-aheads (Daniel)

| # | Owner | Action | Unblocks | Evidence that it happened |
|---|---|---|---|---|
| C1 | Daniel | Go for 3a: A2 (with A1 as prose) on a local branch of the retrained repository, from the runtime pin | step 13 in the retrained repository | Daniel's go-ahead line in the session; the branch and its passing A2 tests in the report |
| C2 | Daniel | Go for 3b: A1 to A5 on a branch of the harness at a commit he names, with `--adjudicator advisory` as the integrated default; for a commit other than the pin `5b60229` the programme re-anchors A3 and A5 and re-measures first | step 13 in the harness | a kit commit whose A3/A5 anchors are for the named commit; the go-ahead line; the applier's `--check` accepting that commit |
| C3 | Daniel (optional) | Only if the agents path is ever routed over the retrained runtime: the routing accepts its contract (`epinoic.specialist-runtime.v0.2.0`) | the "routing accepts runtime" row (REPORTED today) | `ACCEPTED_RUNTIME_CONTRACT_VERSIONS` at a new routing pin lists it |

## Phase D. Website (Bruno)

| # | Owner | Action | Unblocks | Evidence that it happened |
|---|---|---|---|---|
| D1 | Bruno | Merge W0 (PR #26, or a W0 regenerated on the then-current `main`) | G0; merging deploys staging (`staging.yml` on push to `main`) | `check-website.mjs --g0` reads **lifted** on `origin/main` |
| D2 | Bruno | Merge the History pilot stack in his own order (#21 to #25 and #27; #18, tracing, in his release order) and set the pilot deadline (D25: 100 s) | base P on `origin/main`; each merge deploys staging (`staging.yml` on push to `main`) | `check-website.mjs --base` prints P; the deadline in the merged code |
| D3 | Bruno | Re-vendor the kit at the tag and the runtime at the approved pin; resolve the badge text against D27 (the pilot shows "Automatic checks passed" for gate-only answers, which D27 reserves for `formally_checked`) | step 9a's vendored rows; honest labels; merging deploys staging (`staging.yml` on push to `main`) | step 9a PASS on `origin/main`; the page copy matching D27 or a recorded D27 amendment |

## Phase E. Hosting, names and live calls

| # | Owner | Action | Unblocks | Evidence that it happened |
|---|---|---|---|---|
| E1 | Daniel (or the host owner A1 settles) | Choose the host under D7 (USD 30 a month ceiling; at least 3 GiB and 2 vCPU); build the image from the tag, non-root; set by name: `EPINOIC_PROFILE`, `EPINOIC_SERVICE_ENV`, `EPINOIC_SERVICE_TOKEN`, `EPINOIC_SIGNING_KEY` / `_ID`, `EPINOIC_VERDICT_KEY` / `_ID`, `EPINOIC_OVERSEER_SECRET`, `EPINOIC_OVERSEER_AGENTS`, `EPINOIC_FLASH_ROUTER`, `EPINOIC_COMBINATOR`, and `EPINOIC_FIDELITY_REVIEW` only after A5's D6 kit change (this kit's `settings.py` has no such setting yet); every cap at 0, no provider key, not started | D7; the service's secrets | the host's own record and the names listed by the service's preflight, values never shown |
| E2 | Bruno | On the pilot Worker, by name: `TRANSLATOR_SERVICE_TOKEN` (a secret), `TRANSLATOR_MODE`, `TRANSLATOR_BASE_URL`, and the verdict key names (`TRANSLATOR_VERDICT_KEY` / `_ID`) only if D12 as amended is accepted | the Worker's configuration; setting a Worker secret deploys a new version (kit step 9) | Bruno's release record on the website |
| E3 | Bruno | Approve the D14 website caps, the D23 specialist model configuration, and the D15 notice | caps, models, data terms | the website's recorded decisions |
| E4 | Daniel | Enable live calls on the staging service (D14, D15, D23): the provider's data terms, the hard limits, the keys by name (`EPINOIC_ANTHROPIC_API_KEY`; the asynchronous key only if asynchronous work is on), `EPINOIC_TRANSLATION_PROVIDER` and `EPINOIC_ANTHROPIC_MODEL` by name, the five caps; start the service; readiness. Needs A5's D14 kit change first (explicit keys and `check.py --live` are not in this kit) | live calls | the service's preflight passing; `readiness/check.py --live` owner rows set, names only |

## Phase F. Pilot activation (Bruno)

| # | Owner | Action | Unblocks | Evidence that it happened |
|---|---|---|---|---|
| F1 | Bruno | Activate the History pilot (PR #28, "never merge before release review") after his release review, on Access-protected staging only | the live step; merging deploys staging (`staging.yml` on push to `main`) | Bruno's release receipt on the website, with the deployed version and its rollback |

After F1, the production go and every M3 item stay as `DECISIONS.md` lists them under "After M2", each with its
owner's own go.
