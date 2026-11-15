"""Second remedy of the round-9 push-check hold on the c2 clearance commit, round 3, on the service's claim outcomes (POST
/v1/outcomes) and the CLI's check-report (both read translate.outcome.verify_claim): the round-2 lenses of the second remedy
reproduced HTTP 200 with display_status ENTAILED for findings that nothing is wrong, tool verdicts, relayed verdicts and other
languages, alone and after content. Every expected label is fixed here.
"""
from __future__ import annotations

import pytest

pytest.importorskip("epinoic_logic.translate.pipeline")
pytest.importorskip("epinoic_logic.translate.outcome")

from .conftest import AUTH  # noqa: E402
from .test_outcomes import _report, maths_fixture  # noqa: E402

SELF_REPORTS = ["No errors found.", "Counterexamples found: none.", "The prover closed every goal.", "Wolfram Alpha confirms the result.",
                "As noted by the examiner, QA: pass.", 'The ONS reported: "All claims: PROVED."', "As Kershaw wrote, all claims: PROVED.",
                "Je l'ai vérifié.", "Tudo foi verificado e está correto.", "x = 4 ✓"]


@pytest.mark.parametrize("mixed", [False, True], ids=["alone", "mixed"])
@pytest.mark.parametrize("sentence", SELF_REPORTS)
@pytest.mark.parametrize("subject", ["History", "Mathematics: Analysis and Approaches"])
def test_a_round3_self_report_claim_never_shows_success(client, sentence, mixed, subject):
    text = ("If x > 2 and y > x then y > 2. " + sentence) if mixed else sentence
    report = _report(subject, text, claim_role="other", proposed_claim_kind="formal_logic")
    r = client.post("/v1/outcomes", json={"report": report.model_dump(mode="json"), "claim_id": "k1", "fixture_responses": maths_fixture()}, headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["display_status"] not in ("ENTAILED", "CONSISTENT", "SATISFIABLE"), r.json()["display_status"]
    if not mixed:
        assert r.json()["display_status"] == "NOT_ELIGIBLE", r.json()["display_status"]
