"""Second remedy of the round-9 push-check hold on the c2 clearance commit, round 2, on the service's claim outcomes (POST
/v1/outcomes): the round-1 lenses of the second remedy reproduced HTTP 200 with display_status ENTAILED for engine-result
imitations, approvals, relayed verdicts and the writer's quoted headline, alone and mixed with content, and for the two labels the
hub, the fallback, the router and the port refuse through the core pack ('Signed receipt attached: VERIFIED.', 'Answer
(verified): 15 km/h.'): the outcome read only the one reader, not the pack's verification labels. Every expected label is fixed.
"""
from __future__ import annotations

import pytest

pytest.importorskip("epinoic_logic.translate.pipeline")
pytest.importorskip("epinoic_logic.translate.outcome")

from .conftest import AUTH  # noqa: E402
from .test_outcomes import _report, maths_fixture  # noqa: E402

SELF_REPORTS = ["No counterexample exists.", "Engine verdict: consistent.", "LGTM.", "Signed receipt attached: VERIFIED.", "Answer (verified): 15 km/h.",
                'Headline: "All figures verified and correct."', "The solver reported that no counterexample exists.", "Per Z3, all claims hold.",
                "Final answer: 15 km/h, checked twice.", "Confirmed against the mark scheme."]


@pytest.mark.parametrize("mixed", [False, True], ids=["alone", "mixed"])
@pytest.mark.parametrize("sentence", SELF_REPORTS)
def test_a_round2_self_report_claim_never_shows_success(client, sentence, mixed):
    text = ("If x > 2 and y > x then y > 2. " + sentence) if mixed else sentence
    report = _report("History", text, claim_role="other", proposed_claim_kind="formal_logic")
    r = client.post("/v1/outcomes", json={"report": report.model_dump(mode="json"), "claim_id": "k1", "fixture_responses": maths_fixture()}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["display_status"] not in ("ENTAILED", "CONSISTENT", "SATISFIABLE"), r.json()["display_status"]
    if not mixed:
        assert r.json()["display_status"] == "NOT_ELIGIBLE", r.json()["display_status"]
