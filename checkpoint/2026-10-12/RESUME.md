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
