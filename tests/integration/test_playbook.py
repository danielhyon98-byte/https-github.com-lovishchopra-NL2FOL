"""The playbook stays consistent with the kit it drives (integration/PLAYBOOK.md): the rollback rehearsal of PROTOCOL.md
section 14.7 is a step of its own with the exact commands rehearse.mjs and apply.mjs take; the configuration step names
every secret the service and the Worker read (names only, never a value); step 7a runs the flash-router sub-project's
suite and the readiness check on it; and the rollback's "remove the variable" agrees with the router's default."""
from __future__ import annotations

import re
from pathlib import Path

from epinoic_logic.integration.settings import IntegrationSettings

ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK = (ROOT / "integration" / "PLAYBOOK.md").read_text(encoding="utf-8")


def _step(title_start: str) -> str:
    m = re.search(rf"^## {re.escape(title_start)}.*?(?=^## )", PLAYBOOK, re.M | re.S)
    assert m, title_start
    return m.group(0)


def test_the_rollback_rehearsal_is_a_step_with_the_commands_its_scripts_take():
    step = _step("Step 11a.")
    assert "apply.mjs --base M --target <scratch>/website-reader --steps W1" in step
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
    for phrase in ("names that commit and asks for a rehearsal", "worktree add --detach <scratch>/translator-kit", "<commit>`, never a branch",
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
    assert "EPINOIC_FLASH_ROUTER=epinoic_flash_router.port <scratch>/venv/bin/python integration/readiness/check.py" in step7
    assert "--start-service --profile integration-sim" in step7 and "<kit>/flash-router/src" in step7


def test_step_10_applies_the_patch_set_once_on_a_fresh_export_and_verifies_it():
    """Pre-build finding PB3-01: the exact command, run once, with the digest check of the result."""
    step = _step("Step 10.")
    assert "node <kit>/integration/website/apply.mjs --base M --target <scratch>/website-sim --verify" in step
    assert "once, on the fresh export of step 9" in step and "`exact`" in step and "`drift`" in step
    usage = (ROOT / "integration" / "website" / "apply.mjs").read_text(encoding="utf-8")
    assert '"--verify"' in usage and "RESULT.sha256" in usage


def test_step_4_records_the_fetch_date_and_checks_the_w0_draft_without_applying_it():
    """Pre-build finding PB3-06: a missing FETCH_HEAD is recorded as an unknown date; the W0 draft is written into an
    export, read back by the G0 check (lifted) and checked against the website with git apply --check only."""
    step = _step("Step 4.")
    assert "rev-parse --git-path FETCH_HEAD" in step and "no FETCH_HEAD: the date of the last fetch is unknown" in step
    assert "W0/draft-w0.mjs --target <scratch>/w0-export --patch <scratch>/report/W0-docs.patch" in step
    assert "check-website.mjs --g0-export <scratch>/w0-export" in step and "apply --check <scratch>/report/W0-docs.patch" in step
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
    assert "apply-agents.mjs --target <scratch>/agents-a35 --patch" in step13 and "never re-anchor" in step13
    assert "--target <archive copy of the agents repository> [--check] [--patch <file>]" in (
        ROOT / "integration" / "agents" / "apply-agents.mjs").read_text(encoding="utf-8")
