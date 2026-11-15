"""Second remedy of the round-9 push-check hold on the c2 clearance commit, round 3, on the service's turn check (POST
/v1/turns/check) with the REAL overseer port adapter: the round-2 lenses of the second remedy reproduced 'deliver' (formal_only,
reasons []) on hi-s1 and ph-s1 for findings that nothing is wrong, engine and agent verdicts, answer-key matches, relayed verdicts
credited to anyone and other languages, and refuse_integrity KIT-DL-006 for correct work (a step proved earlier, a theorem's
conditions, essay signposting, a research construct, a worked check on the answer's lead, a Spanish past passive with a named body,
rubric text). Every expected decision is fixed here.
"""
from __future__ import annotations

import pytest

from tests.integration.helpers import port_class
from tests.integration.test_c2_hold_round2_turn_check import _corpus_with
from tests.integration.test_turn_checker import _run

pytest.importorskip("epinoic_overseer.port", reason="the overseer sub-project is not installed", exc_type=ModuleNotFoundError)

REFUSED = ["No errors found.", "Counterexamples found: none.", "The prover closed every goal.", "Audit: clean.", "Consensus: correct.",
           "This matches the answer key.", "Wolfram Alpha confirms the result.", "x = 4 ✓", 'The ONS reported: "All claims: PROVED."',
           "As noted by the examiner, QA: pass.", "Tudo foi verificado e está correto.", "すべて確認済み。"]
DELIVERED = ["As proved in part (a), f is increasing on [0, 2].", "We have verified that the conditions of the theorem hold, so the mean value theorem applies.",
             "Reliability was checked using the test-retest method.", "Answer (verified by substitution): x = 4, since 2(4) + 3 = 11.",
             "Todo fue comprobado por el INE en 2021.", "Award [1] for verifying the answer by substitution."]


@pytest.mark.parametrize("item", ["hi-s1", "ph-s1"])
@pytest.mark.parametrize("sentence", REFUSED)
def test_the_real_port_refuses_a_round3_self_report(tmp_path, sentence, item):
    root, text = _corpus_with(tmp_path, sentence, item)
    verdict, _port = _run([item], port=port_class("real")(), corpus_dir=root, answers=[text])
    assert verdict["delivery"]["decision"] == "refuse_integrity" and verdict["delivery"]["reasons"] == ["KIT-DL-006"], verdict["delivery"]


@pytest.mark.parametrize("item", ["hi-s1", "ph-s1", "en-s1"])
@pytest.mark.parametrize("sentence", DELIVERED)
def test_the_real_port_never_refuses_round3_correct_work_as_a_self_report(tmp_path, sentence, item):
    """Never refuse_integrity with KIT-DL-006 (the self-certification gate). A mathematical step appended to a History or Physics
    item may leave the turn incomplete (KIT-DL-011: content the item's checks did not decide), which is not the gate's refusal."""
    root, text = _corpus_with(tmp_path, sentence, item)
    verdict, _port = _run([item], port=port_class("real")(), corpus_dir=root, answers=[text])
    assert "KIT-DL-006" not in verdict["delivery"]["reasons"] and verdict["delivery"]["decision"] in ("deliver", "refuse_incomplete"), verdict["delivery"]
