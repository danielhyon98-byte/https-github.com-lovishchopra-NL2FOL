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
