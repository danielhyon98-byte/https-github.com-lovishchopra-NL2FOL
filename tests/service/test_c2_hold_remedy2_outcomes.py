"""Second remedy of the round-9 push-check hold on the c2 clearance commit, on the service's claim outcomes (POST /v1/outcomes) and
the CLI's ``check-report``: a claim whose text is a self-report ("All values were verified on a GDC and are confirmed correct.",
role ``other``, proposed kind ``formal_logic``) was translated with a faithful-looking fixture (P1 verified, P2 verified ->
correct) and labelled ENTAILED, and the same held with an unrelated maths fixture. Eligibility rule 0 keeps a self-report from the
solver, and the outcome composer never shows a success status for one: its label is NOT_ELIGIBLE. The expected labels are fixed
here, never read from the reader under test.
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("epinoic_logic.translate.pipeline")
pytest.importorskip("epinoic_logic.translate.outcome")

import epinoic_logic.cli as cli  # noqa: E402

from .conftest import AUTH, KEY  # noqa: E402
from .test_outcomes import _report, maths_fixture  # noqa: E402

SELF_REPORTS = ["All values were verified on a GDC and are confirmed correct.",
                "All calculations have been verified by the system and are confirmed.",
                "Z3 found no counterexample to any of the steps.", "Mathematica confirmed every value.", "QA: pass."]
SUBJECTS = ["Mathematics: Analysis and Approaches", "History", "Economics", "Physics"]


@pytest.mark.parametrize("subject", SUBJECTS)
@pytest.mark.parametrize("sentence", SELF_REPORTS)
def test_a_self_report_claim_is_never_labelled_entailed(client, sentence, subject):
    report = _report(subject, sentence, claim_role="other", proposed_claim_kind="formal_logic")
    r = client.post("/v1/outcomes", json={"report": report.model_dump(mode="json"), "claim_id": "k1", "fixture_responses": maths_fixture()}, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["display_status"] == "NOT_ELIGIBLE", body["display_status"]
    assert body["translation"]["status"] == "NOT_ELIGIBLE" and body["verification"] is None


def test_the_cli_never_labels_a_self_report_claim_entailed(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    fixtures_path = tmp_path / "fixtures.json"
    report = _report("History", SELF_REPORTS[0], claim_role="other", proposed_claim_kind="formal_logic")
    report_path.write_text(json.dumps(report.model_dump(mode="json")), encoding="utf-8")
    fixtures_path.write_text(json.dumps(maths_fixture()), encoding="utf-8")
    rc = cli.main(["check-report", str(report_path), "--fixtures", str(fixtures_path), "--adapter", "generic-structured", "--signing-key-hex", KEY.hex(),
                   "--key-id", "cli-key"])
    out = capsys.readouterr().out
    assert rc == 0
    [outcome] = json.loads(out)
    assert outcome["display_status"] == "NOT_ELIGIBLE", outcome["display_status"]


def test_the_composer_never_shows_success_for_a_self_report_a_translator_encoded():
    """Belt and braces: a translator that bypassed eligibility (a fixture that encodes the claim anyway) cannot turn the claim's own
    words into a success label; the composer shows NOT_ELIGIBLE. The clean maths claim keeps its ENTAILED (the control)."""
    from epinoic_logic.translate.outcome import compose_outcome
    from epinoic_logic.translate.pipeline import Translator
    from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider
    from epinoic_logic.engine.runner import verify as engine_verify
    clean = _report("Mathematics: Analysis and Approaches", "If x > 2 and y > x then y > 2.", claim_role="other", proposed_claim_kind="formal_logic")
    tr = Translator(FixtureTranslationProvider(maths_fixture()))
    t = tr.translate(clean.claims[0], clean)
    v = engine_verify(t.problem)
    assert compose_outcome(clean.claims[0], t, v).display_status.value == "ENTAILED"
    selfrep = _report("Mathematics: Analysis and Approaches", SELF_REPORTS[0], claim_role="other", proposed_claim_kind="formal_logic")
    forged = t.model_copy(update={"claim_text_sha256": None})
    claim = selfrep.claims[0]
    assert compose_outcome(claim, forged, v).display_status.value == "NOT_ELIGIBLE"
