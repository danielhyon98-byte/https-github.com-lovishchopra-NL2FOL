"""The kit's decisions (integration/DECISIONS.md): every row of the decision table is decided and points to its entry
in the record the file carries; the section "Kit changes the decisions require" lists the decided behaviours the kit
does not implement yet (each named by its decision); deciding changed no default (the table's defaults are still the
kit's behaviour: spot checks on code); and the file names no model, session or scratch path."""
from __future__ import annotations

import re
from pathlib import Path

from epinoic_logic.integration.compat import COMPATIBILITY
from epinoic_logic.integration.settings import IntegrationSettings

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / "integration" / "DECISIONS.md").read_text(encoding="utf-8")


def _slug(heading: str) -> str:
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def test_every_row_is_decided_and_points_to_its_record_entry():
    table = TEXT[:TEXT.index("## Kit changes the decisions require")]
    rows = [line for line in table.splitlines() if re.match(r"^\| D\d", line)]
    ids = [re.match(r"^\| (D\d+(?: / D\d+)?) \|", r).group(1) for r in rows]
    assert ids[0] == "D1" and ids[-1] == "D33" and len(ids) == 32
    headings = {_slug(line[4:]): line for line in TEXT.splitlines() if re.match(r"^### D\d", line)}
    for did, row in zip(ids, rows):
        status = row.rsplit(" | ", 1)[1]
        m = re.search(r"\[record\]\(#([^)]+)\)", status)
        assert status.startswith("decided") and m, did
        assert m.group(1) in headings and headings[m.group(1)].startswith(f"### {did}. "), did
        assert "| open |" not in row


def test_the_kit_changes_section_names_decisions_and_comes_before_the_record():
    start = TEXT.index("## Kit changes the decisions require")
    end = TEXT.index("## Withdrawn kit tags")
    record = TEXT.index("# Integration kit: decisions of record")
    assert start < end < record
    section = TEXT[start:end]
    named = set(re.findall(r"^- \*\*(D\d+)\*\*", section, flags=re.M))
    assert {"D1", "D2", "D4", "D6", "D13", "D14", "D16", "D25", "D27", "D29"} <= named
    assert "None of these" in section and "changes is made yet" in section


def test_deciding_changed_no_default_of_the_kit():
    # D25: base P keeps the 25 s deadline it was built with until its kit change is made (KIT-HS-016 on base P).
    assert COMPATIBILITY["timing"]["bases"]["P"]["deadline_ms"] == 25000
    # D16: the capabilities object has no `delivery` field yet; D20/D15: no visibility field yet.
    assert "delivery" not in COMPATIBILITY["ports"] and "translator_visibility" not in COMPATIBILITY["repositories"]
    # D2: no per-environment policy list yet; the qualify policy is still a known verdict policy.
    assert "verdict_policies_by_env" not in COMPATIBILITY and "verified-v1-qualify" in COMPATIBILITY["verdict_policies"]
    # D28: the router is detached unless named.
    assert IntegrationSettings.from_env({}).flash_router == "none"


def test_the_record_names_no_model_no_session_and_no_scratch_path():
    assert not re.search(r"claude-(opus|haiku|sonnet)|\b(Opus|Haiku|Sonnet) [0-9]|session_01[0-9A-Za-z]|/tmp/|/root/", TEXT)
    for d in range(1, 34):
        assert re.search(rf"^### D{d}[. ]|^### D9 / D10\.", TEXT, flags=re.M) or d == 10, d
