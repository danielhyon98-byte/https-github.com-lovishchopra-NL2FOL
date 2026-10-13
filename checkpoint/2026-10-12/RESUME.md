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

## 2. State at the checkpoint

(filled in at checkpoint time, below)

## 3. Resume order

Read STANDING_INSTRUCTIONS.md (scratchpad) first; it holds every standing instruction from Daniel.
