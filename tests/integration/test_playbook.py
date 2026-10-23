"""The playbook stays consistent with the kit it drives (integration/PLAYBOOK.md): the rollback rehearsal of PROTOCOL.md
section 14.7 is a step of its own with the exact commands rehearse.mjs and apply.mjs take; the configuration step names
every secret the service and the Worker read (names only, never a value); step 7a runs the flash-router sub-project's
suite and the readiness check on it; and the rollback's "remove the variable" agrees with the router's default."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from epinoic_logic.integration.settings import IntegrationSettings

ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK = (ROOT / "integration" / "PLAYBOOK.md").read_text(encoding="utf-8")


def _step(title_start: str) -> str:
    m = re.search(rf"^## {re.escape(title_start)}.*?(?=^## )", PLAYBOOK, re.M | re.S)
    assert m, title_start
    return m.group(0)


def test_the_rollback_rehearsal_is_a_step_with_the_commands_its_scripts_take():
    step = _step("Step 11a.")
    assert "apply.mjs --base M --target <workdir>/website-reader --steps W1" in step
    assert re.search(r"rehearse\.mjs --full \S+ --reader \S+ \\\n\s+--base \S+ --work \S+", step), step
    usage = (ROOT / "integration" / "rollback" / "rehearse.mjs").read_text(encoding="utf-8")
    assert "--full <export> --reader <export> --base <export> --work <dir>" in usage
    assert "steps 1 to 4 PASS" in step and "NOT RUN" in step
    assert '"--steps"' in (ROOT / "integration" / "website" / "apply.mjs").read_text(encoding="utf-8")


def test_the_configuration_step_names_every_secret_by_name_only():
    step = _step("Step 11b.")
    settings_doc = (ROOT / "src" / "epinoic_logic" / "integration" / "settings.py").read_text(encoding="utf-8")
    for name in ("EPINOIC_SERVICE_TOKEN", "EPINOIC_SIGNING_KEY", "EPINOIC_VERDICT_KEY", "EPINOIC_OVERSEER_SECRET"):
        assert f"``{name}``" in settings_doc and f"`{name}`" in step, name
    worker = (ROOT / "integration" / "website" / "blocks" / "M" / "41-w4-dev-vars.block").read_text(encoding="utf-8")
    assert "TRANSLATOR_SERVICE_TOKEN" in worker and "`TRANSLATOR_SERVICE_TOKEN`" in step
    assert "You set, read, print and log no value" in step
    assert not re.search(r"[0-9a-f]{32,}", step), "no value in the playbook"


def test_step_7a_runs_the_sub_projects_suite_and_the_readiness_check():
    step = _step("Step 7a.")
    assert "(cd <kit>/flash-router && " in step and "-m pytest" in step
    assert "check.py --router epinoic_flash_router.port" in step and "PYTHONPATH=<kit>/flash-router/src" in step
    assert "(connected in phase 2)" not in step.splitlines()[0]
    assert (ROOT / "flash-router" / "pyproject.toml").is_file()


def test_removing_the_router_variable_detaches_it_as_the_rollback_says():
    rollback = (ROOT / "integration" / "rollback" / "ROLLBACK.md").read_text(encoding="utf-8")
    decisions = (ROOT / "integration" / "DECISIONS.md").read_text(encoding="utf-8")
    assert "or remove the variable" in rollback and "unset or `none` (the default)" in decisions
    assert IntegrationSettings.from_env({}).flash_router == "none"


def test_a_pre_build_commit_is_rehearsed_only_on_request_and_reported_as_blocked():
    """A commit without the kit's tag is not a published kit: a session rehearses it only when its user names it, checks
    it out detached at that commit, evaluates every gate (never skips one), continues past the G1 rows marked as
    connected in phase 2 and stops at any other BLOCKER, and reports the rehearsal as blocked by G1."""
    intro = PLAYBOOK.split("## Step 0.", 1)[0]
    rule = intro[intro.index("**A pre-build commit is not a published kit.**"):]
    for phrase in ("names that commit and asks for a rehearsal", "worktree add --detach <workdir>/translator-kit", "<commit>`, never a branch",
                   '"not a published kit: <commit>"', "never skipped or", '"(connected in phase 2: ...)"', "stops the rehearsal",
                   '"rehearsal of an unpublished commit, blocked by G1"', "a commit without the tag stops at step 2"):
        assert phrase in rule.replace("\n> ", " "), phrase
    assert "A pre-build commit is not a published kit" in _step("Step 2.")
    step5 = _step("Step 5.")
    assert "Contract 0.4" in step5 and "contract 0.3 merge" in step5 and "(connected in phase 2: ...)" in step5
    assert "A published kit stops here" in step5 and "rehearsal" in step5 and "A BLOCKER row without that mark stops both" in step5


def test_the_steps_that_cannot_pass_on_a_pre_build_commit_say_what_they_show_there():
    step6 = _step("Step 6.")
    assert "(connected in phase 2)" in step6 and "KIT-HS-006" in step6 and "KIT-HS-007" in step6
    step11b = _step("Step 11b.")
    assert "(connected in phase 2)" in step11b and "KIT-HS-006 named_policies_unavailable" in step11b and "KIT-HS-008" in step11b


def test_step_7a_names_the_router_release_apart_from_the_kit_tag_and_step_7_starts_the_service_with_it():
    step7a = _step("Step 7a.")
    assert "released by its own version, not by the kit tag" in step7a and "Record the" in step7a and "router release" in step7a
    assert "a fault boundary, not a sandbox" in step7a
    step7 = _step("Step 7.")
    assert "EPINOIC_FLASH_ROUTER=epinoic_flash_router.port <workdir>/venv/bin/python integration/readiness/check.py" in step7
    assert "--start-service --profile integration-sim" in step7 and "<kit>/flash-router/src" in step7


def test_step_10_applies_the_patch_set_once_on_a_fresh_export_and_verifies_it():
    """Pre-build finding PB3-01: the exact command, run once, with the digest check of the result."""
    step = _step("Step 10.")
    assert "node <kit>/integration/website/apply.mjs --base M --target <workdir>/website-sim --verify" in step
    assert "once, on the fresh export of step 9" in step and "`exact`" in step and "`drift`" in step
    usage = (ROOT / "integration" / "website" / "apply.mjs").read_text(encoding="utf-8")
    assert '"--verify"' in usage and "RESULT.sha256" in usage


def test_step_4_records_the_fetch_date_and_checks_the_w0_draft_without_applying_it():
    """Pre-build finding PB3-06: a missing FETCH_HEAD is recorded as an unknown date; the W0 draft is written into an
    export, read back by the G0 check (lifted) and checked against the website with git apply --check only."""
    step = _step("Step 4.")
    assert "rev-parse --git-path FETCH_HEAD" in step and "no FETCH_HEAD: the date of the last fetch is unknown" in step
    assert "W0/draft-w0.mjs --target <workdir>/w0-export --patch <workdir>/report/W0-docs.patch" in step
    assert "check-website.mjs --g0-export <workdir>/w0-export" in step and "apply --check <workdir>/report/W0-docs.patch" in step
    assert "never applied" in step
    drafter = (ROOT / "integration" / "website" / "W0" / "draft-w0.mjs").read_text(encoding="utf-8")
    assert "--target <disposable export> [--patch <file>]" in drafter
    assert "--g0-export" in (ROOT / "integration" / "readiness" / "check-website.mjs").read_text(encoding="utf-8")


def test_the_agents_checkout_and_copy_are_fixed_by_the_kit_and_the_install_has_an_offline_route():
    """Pre-build finding PB3-08: the agents candidate is chosen against COMPATIBILITY.json once the kit exists (step 2),
    the copy is of origin's default branch with its commit recorded (step 8), and the install names an offline route."""
    assert "keeps the one whose remote is the agents repository" in _step("Step 1.")
    assert "repositories.agents" in _step("Step 2.")
    step8 = _step("Step 8.")
    assert "refs/remotes/origin/HEAD" in step8 and ".kit-archive-commit" in step8 and "agents/TESTED.json" in step8
    assert "--no-index --find-links <wheelhouse>" in _step("Step 6.")
    step13 = _step("Step 13.")
    assert "apply-agents.mjs --target <workdir>/agents-a35 --patch" in step13 and "never re-anchor" in step13
    assert "--target <archive copy of the agents repository> [--check] [--patch <file>]" in (
        ROOT / "integration" / "agents" / "apply-agents.mjs").read_text(encoding="utf-8")


def test_the_agents_steps_use_the_roles_and_the_pins():
    """The retarget: the agents checkouts are found by either marker (the retrained repository's knowledge-base marker;
    vendored runtimes are reference only), named by role from their remotes (roles.mjs), archived at the pins of
    COMPATIBILITY.json agents_pins (each verified on its branch, the runtime's src tree too) and checked by role; the
    simulation runs the retrained runtime on the website path and the harness on the agents path; the readiness row
    takes the copies by role. Each command is one the kit's scripts take."""
    step1 = _step("Step 1.")
    assert "-maxdepth 7" in step1 and "-name check_kb_set.py" in step1 and "knowledge-bases/_build/check_kb_set.py" in step1
    assert "agents-vendored" in step1 and "REFERENCE only" in step1 and "repositories.agents_harness" in step1
    step2 = _step("Step 2.")
    assert "node <kit>/integration/readiness/roles.mjs <candidate>..." in step2 and "kit_tag_repository" in step2
    assert "repositories.agents_harness" in step2 and "printed `none` (exit status 1) is recorded as not used" in step2
    assert "no agents candidate has role `agents`" in step2 and "NOT RUN with that reason, never PASS" in step2
    assert "never `--depth`" in step2 and "+refs/heads/$B:refs/remotes/origin/$B" in step2
    step3 = _step("Step 3.")
    assert "by role and ref" in step3 and "recorded \"absent\"" in step3 and "<harness>" in step3
    step8 = _step("Step 8.")
    for phrase in ("['agents_pins']", "merge-base --is-ancestor", "src_tree", "<workdir>/agents-runtime", "<workdir>/agents-routing",
                   "<workdir>/agents-harness", "check-agents.mjs --runtime <workdir>/agents-runtime --routing <workdir>/agents-routing",
                   "--harness <workdir>/agents-harness", "never copied, logged or committed", "REPORTED \"routing accepts runtime\""):
        assert phrase in step8, phrase
    step12 = _step("Step 12.")
    assert "--specialist <workdir>/agents-runtime --agents <workdir>/agents-harness" in step12
    step13 = _step("Step 13.")
    assert "<workdir>/agents-work \"$RUNTIME\"" in step13 and "<workdir>/harness-work" in step13 and "agents_pins.harness.commit" in step13
    step14 = _step("Step 14.")
    assert "--agents-runtime <workdir>/agents-runtime" in step14 and "--agents-routing <workdir>/agents-routing" in step14
    assert "--agents-harness <workdir>/agents-harness" in step14 and "agents harness" in step14
    assert "agents-copy" not in PLAYBOOK, "the one-copy archive of the earlier playbook is gone"
    # the commands are the scripts' own
    check_agents = (ROOT / "integration" / "readiness" / "check-agents.mjs").read_text(encoding="utf-8")
    assert all(f'"{flag}"' in check_agents for flag in ("--runtime", "--routing", "--harness", "--vendored", "--kit-tree"))
    assert (ROOT / "integration" / "readiness" / "roles.mjs").is_file()
    assert "-maxdepth 7" in (ROOT / "integration" / "readiness" / "locate.sh").read_text(encoding="utf-8")
    assert '"--specialist"' in (ROOT / "integration" / "sim" / "run_sim.py").read_text(encoding="utf-8")
    check_py = (ROOT / "integration" / "readiness" / "check.py").read_text(encoding="utf-8")
    assert all(f'"--agents-{role}"' in check_py for role in ("runtime", "routing", "harness"))


def test_the_website_recheck_step_never_re_anchors():
    """Step 9a re-checks the website's base, its anchors and the copies the website vendors (the runtime and the kit)
    against the pins, on origin/main and on the unmerged heads the user names, each labelled; it writes nothing and
    never re-anchors: a BLOCKER row is an owner item."""
    step = _step("Step 9a.")
    assert "check-website.mjs --base <website>" in step and "check-website.mjs --anchors <workdir>/website-sim" in step
    assert "check-agents.mjs --vendored <workdir>/website-sim --kit-tree \"$(git -C <kit> rev-parse HEAD:integration)\"" in step
    assert "\"unmerged: <ref> <commit>\"" in step and "never treated as `origin/main`" in step
    assert "re-anchor a block, write a patch set P, or edit an export" in step and "never re-anchor" in step.splitlines()[0]
    assert "no vendored runtime (base M)" in step and "owner item" in step
    assert '"--base"' in (ROOT / "integration" / "readiness" / "check-website.mjs").read_text(encoding="utf-8")
    order = [PLAYBOOK.index(f"## Step {n}") for n in ("9.", "9a.", "10.")]
    assert order == sorted(order), "step 9a comes after the export of step 9 and before the patch set of step 10"


def test_a_rehearsal_continues_after_a_website_stop():
    """R16: a website stop of steps 9 to 12 (base P, an anchor not found or not unique, drift) ends the website steps on
    that export; a rehearsal goes on with steps 13 and 14 and reports it. Nothing re-anchors or edits to get past it."""
    intro = PLAYBOOK.split("## Step 0.", 1)[0].replace("\n> ", " ")
    rule = intro[intro.index("**A website stop does not end a rehearsal.**"):]
    for phrase in ("In steps 9 to 12", "base P without a tested patch set", "`anchor not found`", "`anchor not unique`", "`drift`",
                   "continues with steps 13 and 14", "which website steps did not run and why", "Never re-anchor a block"):
        assert phrase in rule, phrase
    step10 = _step("Step 10.")
    assert "Rehearsal note" in step10 and "continues with steps\n  13 and 14" in step10 and "never the deploying session's" in step10


def test_the_playbook_names_no_model():
    assert PLAYBOOK.splitlines()[0] == "# Playbook: integrate the Z3 kit (for a new Claude Code session)"
    assert not re.search(r"\b(Opus|Sonnet|Haiku|Fable)\b", PLAYBOOK)
    assert not re.search(r"claude-(opus|haiku|sonnet)|session_0[1]|/tmp/|/root/", PLAYBOOK)


# ----------------------------------------------------------------------------------------------- repair 1 (verifier findings)

def _code_lines(step: str) -> list[str]:
    """The lines of a step's code blocks, without the list indentation."""
    out, inside = [], False
    for line in step.splitlines():
        if line.strip() == "```":
            inside = not inside
            continue
        if inside:
            out.append(line[2:] if line.startswith("  ") else line)
    return out


def _sh(script: str, cwd: Path, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(["sh", "-c", script], cwd=str(cwd), capture_output=True, text=True, timeout=120, env={**os.environ, **env})


@pytest.mark.skipif(shutil.which("git") is None or not sys.platform.startswith("linux"), reason="needs git and GNU stat")
def test_step_4_reads_the_websites_own_fetch_date_and_checks_the_w0_draft_on_origin_main(tmp_path):
    """Rehearsal findings: step 4's commands hold wherever they are run from. The fetch date is the website's own
    FETCH_HEAD (git rev-parse --git-path prints a path relative to the checkout, so it is read inside it), and the W0
    draft, made from origin/main, is checked with git apply --check on a second fresh export of origin/main, not on the
    checkout's working tree (behind origin/main, it fails a correct draft), with Git's repository search stopped at
    <workdir> (inside a repository git apply skips the paths outside its directory and would pass unchecked)."""
    step = _step("Step 4.")
    code = _code_lines(step)
    git_env = {"GIT_AUTHOR_NAME": "kit-test", "GIT_AUTHOR_EMAIL": "kit-test@example.invalid", "GIT_COMMITTER_NAME": "kit-test",
               "GIT_COMMITTER_EMAIL": "kit-test@example.invalid"}

    def git(repo: Path, *args: str) -> str:
        return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env={**os.environ, **git_env}).stdout

    def doc(status: str) -> str:
        return "".join(f"line {i}\n" for i in range(1, 8)) + f"Status: {status}\n" + "".join(f"line {i}\n" for i in range(9, 13))
    upstream = tmp_path / "upstream"
    (upstream / "docs").mkdir(parents=True)
    (upstream / "docs" / "current-state.md").write_text(doc("Z3 remains deferred"), encoding="utf-8")
    git(upstream, "init", "-q", "-b", "main")
    git(upstream, "add", "-A")
    git(upstream, "commit", "-q", "-m", "one")
    website = tmp_path / "website"
    subprocess.run(["git", "clone", "-q", str(upstream), str(website)], check=True, capture_output=True)
    (upstream / "docs" / "current-state.md").write_text(doc("Z3 remains deferred (reviewed)"), encoding="utf-8")
    git(upstream, "commit", "-q", "-am", "two")
    git(website, "fetch", "-q", "origin")  # origin/main moves; the checkout's main stays one commit behind
    assert "behind 1" in git(website, "status", "-sb")
    # the fetch date: the website's FETCH_HEAD, never the FETCH_HEAD of the directory the line is run from
    caller = tmp_path / "another-checkout"
    caller.mkdir()
    git(caller, "init", "-q")
    (caller / ".git" / "FETCH_HEAD").write_text("0" * 40 + "\t\tbranch 'main' of elsewhere\n", encoding="utf-8")
    os.utime(website / ".git" / "FETCH_HEAD", (981201600, 981201600))  # 2001-02-03 12:00 UTC
    os.utime(caller / ".git" / "FETCH_HEAD", (1118145600, 1118145600))  # 2005-06-07 12:00 UTC
    [fetch_date] = [line for line in code if "FETCH_HEAD" in line]
    fetch_date = fetch_date.replace("<website>", str(website))
    for cwd in (caller, tmp_path):
        out = _sh(fetch_date, cwd)
        assert "2001-02-03" in out.stdout and "unknown" not in out.stdout, (cwd, out.stdout + out.stderr)
    old_form = f"stat -c '%y' \"$(git -C {website} rev-parse --git-path FETCH_HEAD)\""
    assert "2005-06-07" in _sh(old_form, caller).stdout, "the fixture reproduces the defect the line fixes"
    # the W0 check: a draft made from origin/main
    workdir = tmp_path / "workdir"
    (workdir / "report").mkdir(parents=True)
    draft = tmp_path / "draft"
    subprocess.run(["git", "clone", "-q", str(upstream), str(draft)], check=True, capture_output=True)
    (draft / "docs" / "current-state.md").write_text(doc("Z3 is required on the website path"), encoding="utf-8")
    patch = workdir / "report" / "W0-docs.patch"
    patch.write_text(git(draft, "diff"), encoding="utf-8")
    start = next(i for i, line in enumerate(code) if line.startswith("mkdir -p <workdir>/w0-check"))
    end = next(i for i, line in enumerate(code) if "git apply --check <workdir>/report/W0-docs.patch" in line)
    w0_check = "\n".join(code[start:end + 1]).replace("<workdir>", str(workdir)).replace("<website>", str(website))
    out = _sh(w0_check, tmp_path)
    assert out.returncode == 0, out.stdout + out.stderr
    assert subprocess.run(["git", "-C", str(website), "apply", "--check", str(patch)], capture_output=True).returncode != 0, (
        "the fixture reproduces the defect: the checkout behind origin/main fails the correct draft")
    assert "git -C <website> apply --check" not in step
    # the guard: <workdir> inside a repository, and a draft that does not apply to origin/main
    holder = tmp_path / "holder-repository"
    holder.mkdir()
    git(holder, "init", "-q")
    inner = holder / "workdir"
    (inner / "report").mkdir(parents=True)
    stale = draft / "docs" / "current-state.md"
    git(draft, "checkout", "-q", "--", "docs/current-state.md")  # the test's own clone
    git(draft, "checkout", "-q", "HEAD~1")
    stale.write_text(doc("drafted from an older main"), encoding="utf-8")
    (inner / "report" / "W0-docs.patch").write_text(git(draft, "diff"), encoding="utf-8")
    guarded = "\n".join(code[start:end + 1]).replace("<workdir>", str(inner)).replace("<website>", str(website))
    assert _sh(guarded, tmp_path).returncode != 0, "the guarded check evaluates the patch inside a repository too"
    unguarded = guarded.replace(f"GIT_CEILING_DIRECTORIES={inner} ", "")
    assert _sh(unguarded, tmp_path).returncode == 0, "the fixture reproduces the false pass the guard prevents"


def test_step_6_reruns_a_time_bound_failure_alone_and_never_changes_a_bound():
    """Rehearsal finding: a test that fails only on a time bound on a loaded host is run again alone, and both runs are
    recorded with the host's load; the bound is never changed. Repair 2: the re-run is evidence for the report only, never
    a waiver: the step's stop is the kit's own, unchanged ("any test fails"), so a failing time-bound test stops the step
    whether or not it passes alone (repair 1 had let the step go on when it passed alone; the design does not cover that,
    and only the owner could record such a relaxation)."""
    step6 = _step("Step 6.")
    step = re.sub(r"\s+", " ", step6)
    for phrase in ("A test that fails only on a time bound", "`Timing(...)` report of `tests/timing.py`", "Run that test again alone",
                   "record both runs with the host's load (`uptime`)", "whether it fails alone too", "Never change a bound",
                   "evidence for the report, never a waiver", "the failure stands, and the step stops on it either way"):
        assert phrase in step, phrase
    assert "- **Stop if:** neither works, or any test fails. Never edit tests or code to pass." in step6.splitlines(), step6
    for relaxation in ("the step goes on", "only when it fails alone", "before the failure counts", "timing failure under load"):
        assert relaxation not in step, relaxation
    from tests.timing import Timing  # the report the step names: its fields are the ones the step tells a session to read
    assert {"bound", "wall", "cpu"} <= set(Timing.__dataclass_fields__)


def test_steps_6_and_7_lead_with_the_code_the_current_pre_build_branch_prints():
    """Repair 2: since the contract 0.3 merge the pre-build branch's preflight and start-up stop at KIT-HS-007 (the overseer
    port adapter), so steps 6 and 7 lead with it, quoting the "(connected in phase 2: ...)" mark check.py prints for it;
    KIT-HS-006 stays as the case of a commit from before that merge."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("kit_readiness_check_playbook", ROOT / "integration" / "readiness" / "check.py")
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    note = check._phase2_note(ROOT, "KIT-HS-007 overseer_unavailable: x")
    step6 = re.sub(r"\s+", " ", _step("Step 6."))
    expect = step6[step6.index("- **Expect:**"):step6.index("- **Stop if:**")]
    assert expect.index("KIT-HS-007 overseer_unavailable") < expect.index("KIT-HS-006"), expect
    assert "since the contract 0.3 merge" in expect and "from before that merge it is `KIT-HS-006" in expect, expect
    if note:  # on a commit without the overseer package (this pre-build branch): the exact mark the row carries
        assert note.strip() in expect, (note, expect)
    assert "(connected in phase 2: the overseer port adapter)" in expect
    step7 = re.sub(r"\s+", " ", _step("Step 7."))
    stop = step7[step7.index("- **Stop if:**"):]
    assert stop.index("KIT-HS-007 overseer_unavailable") < stop.index("KIT-HS-006 named_policies_unavailable"), stop
    assert "since the contract 0.3 merge" in stop and "from before that merge" in stop, stop


def test_step_14_names_the_website_patch_set_row_and_drift_blocks_it():
    """Repair 2: step 14 names the row "website patch set (export)" (check.py prints it) and what makes it PASS (step 10's
    export exact) or a BLOCKER (drift, with the drifted files; not applied; not disposable; a base without a tested
    patch set), as step 10 stops on drift; and the simulation runtime copy row is NOT RUN when the website path did not
    run, whatever copy it was given (step 12 says the same of the "Copies" lines)."""
    step14 = re.sub(r"\s+", " ", _step("Step 14."))
    assert '"website patch set (export)" is PASS only when step 10\'s export is `exact`, and a BLOCKER on `drift`' in step14, step14
    for phrase in ("with the drifted files named", "a patch set that is not applied", "an export that is not disposable",
                   "a base without a tested patch set", "also when the website path did not run, whatever copy it was given"):
        assert phrase in step14, phrase
    assert '"website patch set (export)"' in (ROOT / "integration" / "readiness" / "check.py").read_text(encoding="utf-8")
    step10 = re.sub(r"\s+", " ", _step("Step 10."))
    assert 'step 14\'s row "website patch set (export)" is a BLOCKER that names them' in step10, step10
    step12 = re.sub(r"\s+", " ", _step("Step 12."))
    assert "Both name the copy each path was given" in step12 and "a path that did not run says so, with its reason (`not_run`)" in step12
    assert "leaves that row NOT RUN" in step12


def test_a_rehearsal_records_step_13_as_not_run_without_daniels_go():
    """Rehearsal finding: without Daniel's go (and before D20) step 13 is NOT RUN, with no worktree or branch in an agents
    repository; A2 and the A3/A5 applier may run on archive copies only, reported as such."""
    intro = PLAYBOOK.split("## Step 0.", 1)[0].replace("\n> ", " ")
    rule = intro[intro.index("**A website stop does not end a rehearsal.**"):]
    assert "records step 13 as NOT RUN" in rule and "archive copies under `<workdir>` only" in rule and "never on a worktree or a branch" in rule
    step13 = re.sub(r"\s+", " ", _step("Step 13."))
    assert "**Without his go, or before D20**" in step13 and "record this step as NOT RUN" in step13
    assert "with no worktree and no branch in either repository" in step13 and "never as this step" in step13
    assert "apply-agents.mjs --target <archive copy> --check" in step13


def test_step_12_names_each_gates_reason_on_a_pre_build_commit():
    """Rehearsal finding: on a pre-build commit six gates carry the service's refusal and G-EQ-CONTAINED and G-OVS their own
    reasons, quoted from gates.py; step 12 also names the copies the run records."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("kit_sim_gates_playbook", ROOT / "integration" / "sim" / "gates.py")
    gates = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gates)
    step = re.sub(r"\s+", " ", _step("Step 12."))
    assert "six gates (G-EQ-ARENA, G-FAULT, G-INV, G-HON, G-DEL, G-TAMPER) with the service's own refusal" in step
    for reason in (gates.g_eq_contained(None)["reason"], gates.g_ovs(None)["reason"]):
        assert f'"{reason}"' in step, reason
    assert "\"simulation runtime copy\" row is PASS only when the website path ran the runtime pin" in step
    assert "`specialist_commit`, `specialist_contract`, `agents_commit`" in step


def test_step_10_reads_the_outcome_with_its_exit_status():
    step = re.sub(r"\s+", " ", _step("Step 10."))
    assert "`exact` exits 0, `drift` exits 3" in step and "exits 1 with nothing written" in step
    assert "process.exitCode = 3" in (ROOT / "integration" / "website" / "apply.mjs").read_text(encoding="utf-8")


def test_step_14_names_a_row_for_every_unchecked_role_and_the_simulation_copy():
    """Repair 1: a role without a copy is its own NOT RUN row, the one-copy form alone leaves the three NOT RUN, and the
    simulation row for the runtime copy: each name is one check.py prints."""
    step = re.sub(r"\s+", " ", _step("Step 14."))
    check_py = (ROOT / "integration" / "readiness" / "check.py").read_text(encoding="utf-8")
    for row in ("agents runtime", "agents routing", "agents harness", "simulation runtime copy"):
        assert f'"{row}"' in step and f'"{row}"' in check_py, row
    assert "never counts toward a PASS" in step and "with it alone the three rows are NOT RUN" in step


def test_step_2_names_a_role_only_for_github_or_a_loopback_git_proxy():
    step = re.sub(r"\s+", " ", _step("Step 2."))
    assert "(the URL without any user name or password)" in step
    assert "Only a GitHub URL (https, `ssh://git@github.com/` or `git@github.com:`) or a git proxy on this machine's loopback" in step
    assert "a remote on another host, a local path or a file URL names none" in step
