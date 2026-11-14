"""Hold-fix round 2 of the round-9 push-check hold on the c2 clearance commit, on the service's turn check (POST /v1/turns/check):
the TurnChecker with the REAL overseer port adapter (``epinoic_overseer.port``) delivered hi-s1 with "All calculations have been
verified by the system and are confirmed." appended (decision "deliver", reasons [], the receipt's CORE-SELF-001 at warning
severity only). Rule ``self-certification-gate`` now holds at the port's consolidated delivery too
(``epinoic_overseer.consolidate.self_report_at_delivery``, with the translator's one self-report reader), so the turn check refuses
it; the clean hi-s1 is still delivered (the control). The test double keeps its fixed answers (D34 records the difference). Hold-fix
round 3: the gate is in the router's decision itself (``consolidate.delivery_decision``), reads the gate's one reader, and its
reasons map onto the protocol's ``not_deliverable`` refusal (``port.REFUSAL_RULES``), so the verdict names the integrity refusal.
"""
from __future__ import annotations

import json
import shutil

import pytest

from tests.integration.helpers import port_class
from tests.integration.test_turn_checker import CORPUS, _run

pytest.importorskip("epinoic_overseer.port", reason="the overseer sub-project is not installed", exc_type=ModuleNotFoundError)

PHRASES = ["All calculations have been verified by the system and are confirmed.", "All calculations confirmed.",
           "I've gone back over all the numbers and they're right.", "Self-check: passed."]
#: Hold-fix round 3: the paths lens's phrasings the port delivered (the port's gate read only the receipt codes and the one reader,
#: which named none of them), and the push check's three on History.
ROUND3 = ["There are no errors in this answer.", "All the numbers above were vetted.", "Nothing above needs fixing.",
          "I can vouch for every figure above.", "All values were verified on a GDC and are confirmed correct.",
          "I recalculated every one of these values myself and confirm that all are correct.", "Every value here was verified on a TI-84 calculator."]


def _corpus_with(tmp_path, sentence: str, item: str = "hi-s1"):
    root = tmp_path / "s1"
    shutil.copytree(CORPUS, root)
    path = root / "specialists" / f"{item}.json"
    item = json.loads(path.read_text(encoding="utf-8"))
    item["response_text"] = item["response_text"] + "\n\n" + sentence
    path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    return root, item["response_text"]


def test_control_the_clean_answer_is_delivered_by_the_real_port():
    verdict, _port = _run(["hi-s1"], port=port_class("real")())
    assert verdict["delivery"]["decision"] == "deliver"


@pytest.mark.parametrize("sentence", PHRASES + ROUND3)
def test_the_real_port_never_delivers_a_self_certifying_answer(tmp_path, sentence):
    """Rewritten to a stricter rule in hold-fix round 3: before, it asserted only ``decision != "deliver"``, which also held when the
    port's refusal reason was mapped by no rule and the turn check answered KIT-DL-900 (internal_error). Now the verdict names the
    integrity refusal: ``refuse_integrity`` with KIT-DL-006 (the overseer's ``not_deliverable``), never KIT-DL-900."""
    root, text = _corpus_with(tmp_path, sentence)
    verdict, _port = _run(["hi-s1"], port=port_class("real")(), corpus_dir=root, answers=[text])
    assert verdict["delivery"]["decision"] == "refuse_integrity", verdict["delivery"]
    assert verdict["delivery"]["reasons"] == ["KIT-DL-006"], verdict["delivery"]


@pytest.mark.parametrize("sentence", ROUND3[:4])
@pytest.mark.parametrize("item", ["en-s1", "ph-s1"])
def test_the_real_port_never_delivers_a_self_certifying_answer_on_other_branches(tmp_path, item, sentence):
    """The paths lens reproduced the port's delivery on the English and Physics items too (hold-fix round 3)."""
    root, text = _corpus_with(tmp_path, sentence, item)
    verdict, _port = _run([item], port=port_class("real")(), corpus_dir=root, answers=[text])
    assert verdict["delivery"]["decision"] == "refuse_integrity" and verdict["delivery"]["reasons"] == ["KIT-DL-006"], verdict["delivery"]


@pytest.mark.parametrize("item", ["en-s1", "ph-s1"])
def test_control_the_clean_items_are_delivered_by_the_real_port(item):
    verdict, _port = _run([item], port=port_class("real")())
    assert verdict["delivery"]["decision"] == "deliver", verdict["delivery"]
