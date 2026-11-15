"""Second remedy of the round-9 push-check hold on the c2 clearance commit, round 2, on the service's turn check (POST
/v1/turns/check) with the REAL overseer port adapter: the round-1 lenses of the second remedy reproduced 'deliver' (formal_only,
reasons []) on hi-s1, ph-s1 and en-s1 for engine-result imitations, approvals, relayed verdicts and the writer's own quoted
headline or caption, and refuse_integrity KIT-DL-006 for correct work (an event told with a pronoun subject, an outside source's
check, a method step). Every expected decision is fixed here.
"""
from __future__ import annotations

import pytest

from tests.integration.helpers import port_class
from tests.integration.test_c2_hold_round2_turn_check import _corpus_with
from tests.integration.test_turn_checker import _run

pytest.importorskip("epinoic_overseer.port", reason="the overseer sub-project is not installed", exc_type=ModuleNotFoundError)

REFUSED = ["No counterexample exists.", "Engine verdict: consistent.", "Checks: 12/12 passed.", "LGTM.", "Signed off by the reviewer.",
           'As the solver reported, "no counterexample exists".', '"Approved," wrote the overseer.', 'The audit reported: "no errors found".',
           "Final answer: 15 km/h, checked twice.", 'Headline: "All figures verified and correct."', "No figure was left unchecked.",
           "I made sure to verify every value.", "Checked? Yes."]
DELIVERED = ["It was tested at Alamogordo in July 1945.", "These results were confirmed in the 2015 OECD report.",
             "The solution is confirmed by substituting it back into the original equation.",
             "In other words, the IMF found that the figures were sound."]


@pytest.mark.parametrize("item", ["hi-s1", "ph-s1", "en-s1"])
@pytest.mark.parametrize("sentence", REFUSED)
def test_the_real_port_refuses_a_round2_self_report(tmp_path, sentence, item):
    root, text = _corpus_with(tmp_path, sentence, item)
    verdict, _port = _run([item], port=port_class("real")(), corpus_dir=root, answers=[text])
    assert verdict["delivery"]["decision"] == "refuse_integrity" and verdict["delivery"]["reasons"] == ["KIT-DL-006"], verdict["delivery"]


@pytest.mark.parametrize("item", ["hi-s1", "ph-s1", "en-s1"])
@pytest.mark.parametrize("sentence", DELIVERED)
def test_the_real_port_delivers_round2_correct_work(tmp_path, sentence, item):
    root, text = _corpus_with(tmp_path, sentence, item)
    verdict, _port = _run([item], port=port_class("real")(), corpus_dir=root, answers=[text])
    assert verdict["delivery"]["decision"] == "deliver", verdict["delivery"]
