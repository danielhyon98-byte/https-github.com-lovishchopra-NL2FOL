"""The STEM fault-class probes compare each probe with the untampered copy of its own task (``scripts/overseer/stem_probes.py``).

A translation probe's untampered copy has the planted claim's recorded translation removed, so two translation probes on one
task but on different claims must not share a copy: on 25 Oct the control units-translation-table-base-control (claim g1.1) was
compared with the copy made for givens-translation (claim g2.3), and the untouched claim s1.1, which reads differently there,
showed its INT-REQ-006 as a new finding and failed the contained run's gate stem_fault_classes_named. With the recorded round r7
present (``EPINOIC_ARENA_ROUNDS``), the two probes are run in that order and the control stays clean."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import stem_probes as SP  # noqa: E402

ROUNDS = Path(os.environ["EPINOIC_ARENA_ROUNDS"]) if os.environ.get("EPINOIC_ARENA_ROUNDS") else None
HAS_R7 = ROUNDS is not None and (ROUNDS / "r7" / "specialists").is_dir()
PROBES = {p.probe_id: p for p in SP.PROBES}


def test_translation_probes_on_one_task_but_different_claims_have_their_own_untampered_copies():
    shared, control = PROBES["givens-translation"], PROBES["units-translation-table-base-control"]
    assert shared.key == control.key and shared.stems == control.stems
    assert shared.translation[1] != control.translation[1]
    assert SP._base_key(shared) != SP._base_key(control)


def test_probes_on_the_same_claim_or_without_a_translation_still_share_a_copy():
    control, wrong = PROBES["units-translation-table-base-control"], PROBES["units-translation-table-wrong"]
    assert control.translation[:2] == wrong.translation[:2] and SP._base_key(control) == SP._base_key(wrong)
    answers = [p for p in SP.ANSWER_PROBES if p.translation is None]
    by_task: dict[tuple, set] = {}
    for p in answers:
        by_task.setdefault((p.stems, p.key), set()).add(SP._base_key(p))
    assert all(len(keys) == 1 for keys in by_task.values())
    assert all(SP._base_key(p) != SP._base_key(control) for p in answers if (p.stems, p.key) == (control.stems, control.key))


@pytest.mark.skipif(not HAS_R7, reason="the recorded round r7 is not present (set EPINOIC_ARENA_ROUNDS to the directory holding it)")
def test_the_table_unit_control_stays_clean_after_a_probe_on_another_claim_of_its_task(tmp_path):
    doc = SP.run_probes(tmp_path / "probes", ROUNDS, probes=(PROBES["givens-translation"], PROBES["units-translation-table-base-control"]))
    row = next(r for r in doc["probes"] if r["probe_id"] == "units-translation-table-base-control")
    assert row["outcome"] == "clean", row
    assert row["new_receipt_findings"] == [], row["new_receipt_findings"]
