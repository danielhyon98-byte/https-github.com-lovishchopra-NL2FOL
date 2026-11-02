# Resume after the weekly limit of 2 Nov 2026 (limit expected ~17:00-18:00 UTC Mon 2 Nov; it resets Fri 6 Nov 16:00 UTC)

S = /tmp/claude-0/-home-user/a7c3c8b5-0245-5e75-80f1-83ca77b220e6/scratchpad, R = /home/user/https-github.com-lovishchopra-NL2FOL,
dev branch = claude/z3-verification-engine-plan-nk3luq (origin = danielhyon98-byte/https-github.com-lovishchopra-NL2FOL),
main repository = Epinoic-AI/Epinoic-Logic-Translator (remote "epinoic"; the old Bruno-ios URL redirects; uploads only via the S publishers).

## Daniel's latest instruction (2 Nov ~14:40 UTC): "finish round 8 then create handoff for yourself"
This section is that handoff. Order from here: (1) FINISH ROUND 8 (its fix round, verification, commit, push check, upload,
README note, prototype docs and their commit and upload); (2) update this section and KNOWLEDGE/01-STATE.md, push a checkpoint;
(3) then the governing order continues unless Daniel says otherwise: the architecture step after round 8 (his budget choice 1/2/3
is still unanswered; default option 1 = do it; options 2/3 = write S/wf/phase2/DECISION.json {"skip_architecture": true}), arena
rounds 9 and 10 with their fixes (Daniel 31 Oct), then the handoff protocol (KNOWLEDGE/05-HANDOFF-PROTOCOL.md) with a handoff
refresh on docs/final-z3-handoff after each verified upload. No optimisation work, no website work, no new repositories.

## Done and verified (2 Nov)
- verified-updates carries the code of development commit 16d5a4a (upload commit 7a939fd, 10:52 UTC; later commits there are the
  publisher's hourly notes). 16d5a4a = 6947c2d's code + documentation; 6947c2d = the gate-fixed integrated translator (gate commits
  35f1be1, 7f9ec18, 5c8577e, 1965f07: five rounds, 206 findings fixed incl. all 38 critical) + the fix of the gate-round-1 regression
  that failed the contained gate stem_fault_classes_named (a correct 50.0 cm3 -> 0.0000500 m3 conversion flagged as introduced).
  Simulation (SIMULATION OK, cached in S/simcache/translator-16d5a4a...txt): suite 16,876 passed, 45 deselected, 0 failed (run on
  exactly 16d5a4a; evidence S/sim-evidence/16d5a4a-run1-cut-at-2h.txt), harness r1 30/30, r1-adv 150/151, r2-r6 46/46, r7 177/177,
  contained run r2-r5 46/46 and r7 177/177 with 358/358 tamperings. Read back: src/ tests/ integration/ scripts/ pyproject.toml identical.
- docs/final-z3-handoff d3af9f3 (report, website launch steps, instructions for Bruno; refreshed for 16d5a4a; read back).
- Checkpoints: origin checkpoint/2026-10-12, pushed hourly (S/make_checkpoint.sh build && ... commit).

## Round 8 state (phase 2 run wf_eee12853-0ae)
- Script S/wf-scripts/phase2-cont.js, args = the JSON in S/wf/phase2-cont-args.json (continueAfterRound8 true). Journal:
  /root/.claude/projects/-home-user/a7c3c8b5-0245-5e75-80f1-83ca77b220e6/subagents/workflows/wf_eee12853-0ae/journal.jsonl.
- Done: relay, translators, combinator, harness:c1, overseer prep, scalability:c1, the greenlight judges, the five overseer lenses
  (results-audit, communication-fidelity, adversarial-live, stem-integration, translation-fidelity). Fix round "clearance-c1" since
  ~10:20: fix:parsers returned ~14:2x; fix:stem (since ~10:20) and fix:core (since ~14:2x) were still running when this was written.
- R holds the fixers' UNCOMMITTED edits (38 paths at 14:07). Never commit them by hand (the stop hook asks; decline): the pipeline
  commits after a green verification as "Fix the c1 clearance findings".
- STOP BEFORE THE LIMIT: I stop phase 2 (TaskStop) at about 98% weekly usage so no step runs into the limit and records a null
  result. The time of the stop and the agents it killed are recorded in KNOWLEDGE/01-STATE.md (last entries).
- TO RESUME (after the reset, same container): check `uptime` (a VM restart kills background jobs and monitors but keeps the disk);
  Workflow({scriptPath: "S/wf-scripts/phase2-cont.js", resumeFromRunId: "wf_eee12853-0ae", args: <exact JSON of
  S/wf/phase2-cont-args.json>}). Completed agents replay from cache; killed fixers re-run and find their partial edits in R. Then check
  the journal: no completed label may be restarted under a new key (a changed prompt). If some step after the stop recorded a null or
  error result, dry-run first with S/dryrun-crit/dry_resume4.mjs (args: script, argsfile, cached.json, out.json, run|skip).
- Remaining round-8 steps in the script: fix round -> verify (full suite ~85 min; the pipeline's verify runs WITHOUT
  EPINOIC_ARENA_ROUNDS, so round-dependent tests and STEM probes are skipped there) -> commit + push origin -> push-check:c1 (writes
  S/push-check/<sha>.json; the publisher uploads a "Fix the c1 clearance findings" commit only with hold=false) -> push:c1 ->
  readme:c1 -> prototype docs + their own verify and commit ("Prototype: integrated translator after round 8") -> decision:architecture.
- THE ROUND-8 UPLOAD WILL NEED HELP: push:c1's agent runs presim.sh as one background command; a full simulation now takes ~2.2 h and
  background commands die at 2 h, so expect "NOT PUSHED" (phase 2 then continues). Then from the main session: copy
  S/run_sim_16d5a4a.sh to run_sim_<sha>.sh with T = the round-8 final commit and FLOOR = T if its "Harness after the change" line
  records r1, r1-adv, r2..r7 (else the newest commit that does); do NOT set SIM_SKIP_SUITE unless the suite already passed on exactly
  T; start it with `setsid nohup bash ... > log 2>&1 < /dev/null &`; it caches like presim.sh and runs event_push.sh (uploads only on
  SIMULATION OK). Read back verified-updates (Source-Commit = T; code paths identical). Before any upload, run the STEM probes and the
  round-dependent tests yourself if the fixers touched translate/ or stem/ (S/repro-sim/probe.sh SHA): the gate's regression showed
  the pipeline's verify cannot see them.
- After the prototype commit: upload it the same way, then S/release_prototype.sh (branch "prototype" + tag "prototype-round8";
  read the script first), then refresh the handoff: copy S/wf-scripts/handoff-refresh-1nov.js (phases Write, Check, Fix, Amend; args
  in S/handoff/refresh-1nov-args.json as the model), then S/handoff/fill.py and S/handoff/push_handoff.sh, then read back.

## Machinery and 2 Nov lessons (details in KNOWLEDGE/04-PROCEDURES.md)
- Hourly routine: trigger trig_018DjeNCSCGD5yGC4WwaWxDz fires ~:58 (steps A-D in its prompt; A only when R is clean). It may fire up
  to ~13 min late: run S/hourly_push.sh --now then.
- Watchdog: a 30-min Monitor running `python3 -I S/watchdog.py | grep -vE <filters>` plus a df check every 120 s; re-arm on expiry.
- publish_final.sh reads the FINAL commit's message: it needs "Harness after the change: <rN a/b ...>" and "Suite: N passed ... 0 failed".
  A commit without them is held ("records no harness counts"); add a documentation commit that records them (precedent 16d5a4a).
- simulate.sh replays only the rounds the SOURCE commit's harness line records; a final commit must record every round.
- A workflow agent's background job dies when the agent ends; long jobs belong to the main session, detached.
- Keep >= 5 GB free disk (df -Pm /); the watchdog alarms below 3 GB.

## Open items and known defects
- Daniel's budget choice 1/2/3 (unanswered; default 1).
- MAJOR known defect: the synthesis ledger's read and quotation bounds are spent in claim order, so padding can push a changed date or
  an invented quotation past them: only an INT-LEDGER-026 warning, release allowed, delivered "not verified" instead of withheld.
- KIT-HS-007: the integration service does not start with its default overseer port (epinoic_overseer.port is missing); the
  architecture step builds it.
- Website main moved to b2ffbcc (merges PR #23, carries src/chat/pilot.js): the kit reads it as base P, which has no patch set.
- overseer-prototype held at 9547fc9 (its candidates fail the contained run: 235 of 254 faults named, 3 false alarms).

---------------------------------------------------------------------------------------------------------------------------------
Older sections below (25-31 Oct) are history; where they disagree with the section above, the section above wins.

> 25 Oct 20:46 UTC (weekly limit): DONE: upload 869bf84 (= dev 404aee2), handoff docs/final-z3-handoff d4028c9 (verified).
> Port of argument diagnostics: UNVERIFIED step-1 work on origin argdiag-port 32842ec; continue after the reset per
> KNOWLEDGE/01-STATE.md (entry 25 Oct 20:46). Round 8 only after the reset (Daniel).

> 25 Oct ~17:55 UTC: the argument-diagnostics merge FAILED (argdiag-final forked 17 Oct; contradictory duplicate fixes). Daniel decided:
> over-limit requests are REJECTED (INT-REQ-009); STEM tolerance keeps the sum rule h(b)+h(w); now upload 404aee2 and refresh the
> handoff; AFTER the reset port argument diagnostics onto the dev head (dev behaviour wins every contradiction), re-run its corpora,
> then phase 2's integration, gate and round 8.

> 25 Oct ~15:15 UTC, Daniel: "just aim to finish phase 2 merger and do not proceed with round 8 testing until after the weekly
> reset. then following that prepare handoff for updated integration of new z3 into the website". Phase 2 returns {paused} after
> the argument-diagnostics merge; resume it (remove the pause return in phase2-pipeline.js) only after Fri 30 Oct 16:00 UTC.
> Then the handoff refresh (task #160). See KNOWLEDGE/01-STATE.md, entries of 25 Oct 15:00-15:15.

# Resume after the weekly limit of 25 Oct 2026 (final checkpoint ~08:05 UTC; limit resets Fri 30 Oct 16:00 UTC)

Read KNOWLEDGE/01-STATE.md (entries 00:00-08:00 of 25 Oct) first. Where everything stood:
- DEV BRANCH (origin claude/z3-verification-engine-plan-nk3luq) = 3adfd73 "Merge the logic-checking overseer agents into
  the translator" (independently verified: suite 10503 passed, 0 failed; harness r1-r7 = baseline). Not yet on
  verified-updates: its pre-upload simulation failed once on 1 unnamed test under load 11-14 (the 167 round-dependent
  tests pass); a second rerun was running (log scratchpad/presim-3adfd73-rerun2.log). simulate.sh now names failing tests.
  To upload: if simcache/translator-3adfd73...txt says SIMULATION OK, run event_push.sh; else rerun presim.sh then
  event_push.sh (detached with setsid nohup: the merged suite takes ~38-45 min).
- PHASE 2 wf_1683c1c3-d71 (script .worktrees/scripts/phase2-pipeline.js, args scratchpad/wf/phase2-args.json): in the r7
  handoff fix round (blocker+major only; minors are known defects). fix:stem and fix:core returned; fix:parsers and
  fix:overseer were running; then the handoff fixer, verify, commit "Fix the r7 handoff findings". The main checkout
  holds their uncommitted edits: do NOT commit them by hand. Resume: Workflow({scriptPath, resumeFromRunId:
  "wf_1683c1c3-d71", args: <phase2-args.json>}); agents that were running re-run (their partial edits stay in the tree;
  the re-run fixers see them).
- ARGDIAG ACCURACY wf_66515820-135 (script scratchpad/wf-scripts/argdiag-accuracy.js, no args): accfix:2 was running on
  the argdiag-integ worktree index (BEFORE ref argdiag-accfix-before 4267cb3). Resume with resumeFromRunId. Then commit
  the index on local branch argdiag-final with wf/argdiag/commit-msg.draft.txt (fresh Suite/Harness lines, known defects),
  simulate.sh translator argdiag-final argdiag-final; phase 2's wait:argdiag merges it.
- OVERSEER UPLOAD (overseer-prototype) held by overseer_gate policy (a) on 502fcff; the merge 3adfd73 carries the rebuild.
- Daniel 23 Oct ~19:02: "dont worry about weekly usage" (only the final checkpoint applies). Round 8 not started.

# Resume (updated 2026-10-17): read KNOWLEDGE/ first

The compact knowledge files are in tools.tar.xz under KNOWLEDGE/ (00-READ-FIRST, 01-STATE, 02-PRIORITIES, 03-RULES,
04-PROCEDURES). They say where every task stands, what to do next in order, Daniel's rules and how the machinery works.
The checkpoint is refreshed every hour; work in progress captured mid-edit is a snapshot, so re-run a step whose agent was
running at checkpoint time. The restore steps below are unchanged.

# Resume from the 2026-10-12 checkpoint

This folder is everything needed to continue in a fresh container. It is pushed to the backup branch
`checkpoint/2026-10-12` of origin (Daniel's dev repo), under checkpoint/2026-10-12/. Never published to Bruno's repository.

## 1. Restore (fresh container)

```bash
R=/home/user/https-github.com-lovishchopra-NL2FOL      # dev checkout (origin = danielhyon98-byte/...-NL2FOL)
S=<this session's scratchpad directory>                  # the old one was /tmp/claude-0/-home-user/a7c3c8b5-0245-5e75-80f1-83ca77b220e6/scratchpad
cd "$R" && git fetch origin claude/z3-verification-engine-plan-nk3luq && git fetch origin checkpoint/2026-10-12
C=$(git rev-parse FETCH_HEAD)
OUT=/home/user/epinoic-checkpoint-2026-10-12; mkdir -p "$OUT"
for f in $(git ls-tree --name-only "$C" checkpoint/2026-10-12/); do git show "$C:$f" > "$OUT/$(basename "$f")"; done
cd "$OUT"; ls *.part* 2>/dev/null && for b in $(ls *.part00 | sed 's/\.part00$//'); do cat "$b".part* > "$b"; done
sha256sum -c SHA256SUMS
```

1. Branches: `git -C "$R" bundle verify $OUT/branches.bundle`, then
   `git -C "$R" fetch $OUT/branches.bundle 'refs/heads/*:refs/heads/*' 'refs/checkpoint/*:refs/checkpoint/*'`
   (skip the checked-out dev branch if git refuses it; it equals origin). Branches already merged into the dev branch
   (stem-build, import/translator-baseline) are not in the bundle; recreate every name from branch-tips.txt:
   `while read -r ref sha; do git rev-parse -q --verify "$ref" >/dev/null || git update-ref "$ref" "$sha"; done < $OUT/branch-tips.txt`
2. Bruno's remote: `git -C "$R" remote add epinoic https://github.com/Bruno-ios/Epinoic-Logic-Translator.git && git -C "$R" fetch epinoic`
   (if access is refused, attach the repository with add_repo, push access).
3. Worktrees (see worktrees.txt): `git worktree add .worktrees/overseer overseer-build`, likewise review-engine,
   review-metrics, review-translate, review-stem-checks, review-stem-channel, `.worktrees/stem stem-build`,
   `.worktrees/import import/translator-baseline`. Then `tar -C "$R/.worktrees" -xJf worktree-scripts.tar.xz`
   (restores .worktrees/scripts/phase2-pipeline.js).
4. Work in progress: `tar -xJf wip.tar.xz`; for each wip/<name>/ the checkout is reproduced by checking out HEAD,
   then either `git read-tree -m -u <staged-commit>` style restore from refs/checkpoint/2026-10-12/<name>-staged
   (`git checkout <ref> -- .` then `git reset --soft HEAD`; for a merge also write MERGE_HEAD/MERGE_MSG into the
   worktree's git dir), or `git apply --index staged.patch && git apply unstaged.patch`, plus untracked.tar.xz.
5. Tools and records: `tar -C "$S" -xJf tools.tar.xz` (scripts, wf-scripts, sim mocks, STANDING_INSTRUCTIONS.md,
   runs.json, feedback-design.json, round8-prep, clearance/c1, push-check, simcache, c1-design, publisher-next, and the
   recorded arena rounds arena/r* that simulate.sh replays before every upload).
   Knowledge bases (not in the pushed tier): `git -C "$R" archive epinoic/docs/specialist-kb-v4 | tar -x -C "$S/kb-v4"`
   (check the layout round8-prep/pre.json expects). If $S differs from the old path, rewrite it in the tools:
   `grep -rl OLD_S "$S" --include='*.sh' --include='*.py' --include='*.js' | xargs sed -i "s#OLD_S#$S#g"`.
   The full scratchpad, workflow journals and workflow reports are in the local copy only
   (/home/user/epinoic-checkpoint-2026-10-12/local-only/) and survive only while that container lives.
6. Environments: `python3 -m venv "$S/z3venv" && "$S/z3venv/bin/pip" install -e "$R[dev,service,providers]"`;
   simulate.sh builds its own overlay venv per run.
7. Workflow journals: publish_overseer.sh gates an overseer candidate on its build or rebuild workflow journal
   (runs.json). A candidate committed before the checkpoint and not yet published needs the local-only journals;
   without them it is re-validated by a fresh workflow run (audit + eval + commit agents) before upload.
8. Triggers: re-enable the hourly (:58) and quarter-hour (:13, :28, :43) routines if they were paused.
9. Check: `bash $S/presim.sh` (simulates any unpublished candidate), `python3 -I $S/status.py`.

## 0a. UPDATE 16 Oct 20:0x UTC: the 8 preserve/2026-10-16/* branches ARE uploaded (pushed through the old address, which GitHub
redirects to Epinoic-AI/Epinoic-Logic-Translator; read back 8/8 SHA and tree). verified-updates is now 90e3587 (hourly note;
backup/verified-updates-previous = a91a4f9). A new session is only needed if that address stops working.

## 0. 16 Oct 2026: move to a NEW SESSION on the canonical repository (read this first)

The private destination is now **Epinoic-AI/Epinoic-Logic-Translator** (transferred from Bruno-ios; same repository).
Its default branch is import/translator-baseline; **verified-updates = a91a4f977b39a155722d50fe2808434a35ae315e** (uploaded,
the verified STEM-merged translator, source 83e97e9). overseer-prototype = 9547fc9.

Why a new session: the old session (container checkout /home/user/epinoic-logic-translator) attached the repository under
its old name. Measured 16 Oct 19:4x UTC, identity danielhyon98-byte:
- `gh api repos/Epinoic-AI/Epinoic-Logic-Translator --jq '{full_name,default_branch,permissions}'` -> exit 1, HTTP 403:
  "GitHub access to this repository is not enabled for this session. Use add_repo to request access. ..."
- add_repo(Epinoic-AI/Epinoic-Logic-Translator, push) -> refused: "a different repository named "epinoic-logic-translator"
  (bruno-ios/epinoic-logic-translator) is already attached to this session ... Same-named repositories from different
  owners can't share a session; start a new session with epinoic-ai/epinoic-logic-translator as a source.
  (This is a checkout-layout limit, not an access problem.)"
- git over the old URL: HTTP 403 "Claude doesn't have GitHub access to Bruno-ios/Epinoic-Logic-Translator ...".

New session, in order:
1. Start it with BOTH sources: Epinoic-AI/Epinoic-Logic-Translator (choose branch **verified-updates** explicitly, not the
   default) and danielhyon98-byte/https-github.com-lovishchopra-NL2FOL (holds this checkpoint). Do NOT attach
   bruno-ios/epinoic-logic-translator.
2. In the NL2FOL clone: fetch branch checkpoint/2026-10-12, extract checkpoint/2026-10-12/* (section 1), `sha256sum -c`,
   `git bundle verify`, then `git fetch <bundle> 'refs/heads/*:refs/heads/*' 'refs/checkpoint/*:refs/checkpoint/*'`
   (the bundle's prerequisites are this repository's dev branch, so fetch it HERE, not into the Epinoic clone).
3. Read-only check: `gh api repos/Epinoic-AI/Epinoic-Logic-Translator --jq '{full_name,default_branch,permissions}'`;
   `git ls-remote https://github.com/Epinoic-AI/Epinoic-Logic-Translator` -> verified-updates must still be a91a4f9 and no
   preserve/2026-10-16/* may exist yet. Read the repository's CLAUDE.md / instructions.
4. Re-run `bash prepare_preserve.sh scan` (tools.tar.xz) on the fetched refs (must stay all zeros), then ONE ordinary push
   from the NL2FOL clone, no force: `git push https://github.com/Epinoic-AI/Epinoic-Logic-Translator
   'refs/heads/preserve/2026-10-16/*:refs/heads/preserve/2026-10-16/*'`. Pushes only the preserve commits (parent a91a4f9)
   and their trees; no development history.
5. Read back: ls-remote SHAs equal the local refs below, and each remote ref's tree equals the local tree.
   Never move verified-updates, overseer-prototype or import/translator-baseline for this.

Preservation snapshot branches (one commit each, parent a91a4f9, scanned 16 Oct: 0 credentials, 0 generated files,
0 files over 5 MB, 0 scratch paths, 0 session ids, 0 model names; positive control caught all four planted patterns):
  - preserve/2026-10-16/overseer-ef4ba9f 405ddf70f7bc483d33c0797757210946c0f11d61
  - preserve/2026-10-16/overseer-rebuild-wip d149738cc9812938651e1ca42a67eeb968b5b84a
  - preserve/2026-10-16/review-engine 118bc0dbccd766666fc1d68ce3392b9e17a7842a
  - preserve/2026-10-16/review-fixes-wip e2dce37ce26b8723cbbef56eb2e147b3892e90b9
  - preserve/2026-10-16/review-metrics d3a148ec4a2b4cb975f525dda5270824be790d98
  - preserve/2026-10-16/review-stem-channel 640abcc6d216d133ab56c4c89d8e105a95b4ec4a
  - preserve/2026-10-16/review-stem-checks 18d7202f182e42c42210e3f2f14a16ae35d94458
  - preserve/2026-10-16/review-translate f24d8b121dfcfd56ba1ae3cb1c76d1a5b5b45877
  overseer-ef4ba9f = committed overseer fault corrections (not through the upload gate); overseer-rebuild-wip and
  review-fixes-wip = uncommitted on-disk states (UNVERIFIED; their last independent checks were not clean);
  review-engine/translate/metrics and review-stem-checks/channel = committed fix branches (not independently verified).

Stopped for the recovery task (no paid calls authorised): review-fix second repair (run wf_b526acb3-6c2) and overseer
second repair (run wf_92057cdf-3e2); all four routines paused. Resume development only when Daniel asks.

## 2. State at the checkpoint (2026-10-13 ~00:20 UTC; Daniel: stop at a safe checkpoint, tokens limited)

Uploaded and verified (durable):
- Bruno's repo: verified-updates a91a4f9 = the STEM-merged translator (source 83e97e9; simulation OK: suite 4353 passed,
  every recorded round at its record, r7 177/177); backup/verified-updates-previous 5573a06.
  overseer-prototype stays 9547fc9 (candidates 6adbd64/87eaf86 fail the r7 contained gates: 235/254 named, 3 false alarms).
- origin dev branch claude/z3-verification-engine-plan-nk3luq at 361cc4e.

Committed locally, in branches.bundle (not uploaded):
- overseer-build ef4ba9f: overseer fault corrections (TRN-006 by engine evidence, adjudicated genuine faults, STEM-ready
  checks, pack 1.2; contained r2-r5,r7: 0 false alarms, 2/2 adjudicated raised, 250/254 named, tamper 110/110, 2385 passed).
- review-engine f902edd, review-translate 6c3b802, review-metrics 2b1cad3: fixes for Bruno's nine Update-7 findings
  (each with regression tests; not yet integrated).
- review-stem-checks 50611e6, review-stem-channel eb66038: STEM review fixes S1-S7 (not yet integrated).

Work in progress, stopped on purpose and saved exactly (wip.tar.xz + refs/checkpoint/2026-10-12/* in the bundle):
- wip/main: the review-fix integration into the dev checkout, partly staged (workflow wf_b526acb3-6c2, step "integrate";
  fix:engine/translate/metrics finished). Not verified, not committed.
- wip/overseer: the merge of 47b8c21 into overseer-build (workflow wf_92057cdf-3e2, step "rebuild:merge"). Its own task
  list at the stop: conflicts resolved and staged, missing regression tests added, knowledge pack updated; still open:
  making the overseer correct on the merged translator (STEM ids, receipts, word bounds, FIXED_SEVERITY INT-SUBJ-004,
  RES-004 STEM policies, E112 vs OVS-TRN-006/010), then measurement (suite, harness on every round, contained run
  r2-r5,r7) and docs. Not audited, not committed.

Paused: the routines (hourly :58 trig_018DjeNCSCGD5yGC4WwaWxDz; quarter-hour trig_019NZ6zdBPyFosjgF144dBeL,
trig_01TW8XXcXTUpeEynv9GZHjBv, trig_01R3937JHkQkWazdSZZtrhLH), the presim/event-push loop and the watchdog.
Permission notes: release_prototype.sh was refused by the permission check ("production deploy"); it is needed only
after round 8 and needs Daniel's approval then. Checkpoints go to the backup branch only (Daniel's choice).

## 3. Resume order (Friday)

Read STANDING_INSTRUCTIONS.md (in tools.tar.xz) first; it holds every standing instruction from Daniel.
1. Restore (section 1), including both work-in-progress states; re-enable the routines; restart the presim/event-push
   loop and the watchdog.
2. Review fixes: finish the integration from wip/main (workflow script wf-scripts/external-review-fixes.js; the integrate
   prompt already carries a resume note; if the journal is gone, run integrate + verify as a fresh workflow over the three
   review branches), independent verification, simulate.sh on the staged tree, write REVIEW_FIXES_README.md, commit
   "Fix the external review findings", push origin; event_push.sh uploads it to verified-updates after its simulation.
3. Overseer rebuild: finish rebuild:merge from wip/overseer (wf-scripts/overseer-rebuild.js; args in runs.json /
   rebuild-notes.txt with the RESUMING note), then audit (bugs, faults, infected code), eval, commit; presim.sh, then
   publish_overseer.sh uploads to overseer-prototype only if every gate passes. Refresh its internal translator after step 2.
4. STEM review fixes: integrate review-stem-checks/channel, retest every finding of both reviews, README, commit, push.
5. Overseer STEM accommodation stage with the specialist feedback function (feedback-design.json), then phase 2
   (round 8 with the push check and immediate push, o1, prototype, rounds 9-10, scaling up to 32, final release).
