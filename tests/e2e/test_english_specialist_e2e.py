"""End to end for the English specialist example: adapter -> Translator(fixture provider) -> real engine -> outcome.

No network: the fixture provider replays IR built from Example 1 of the specialist's
knowledge documents; everything downstream is the real pipeline and the real Z3.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters import get_adapter
from epinoic_logic.adapters.english_specialist import fixtures as fx
from epinoic_logic.engine import verify as engine_verify
from epinoic_logic.engine.provenance import verify_signature
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.statuses import DEFINITIVE, SCOPE_STATEMENT, VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate import Translator, TranslationStatus as T, verify_claim
from epinoic_logic.translate.contracts import SpecialistReport
from epinoic_logic.translate.grounding import check_claim_sources
from epinoic_logic.translate.providers import FixtureTranslationProvider

CFG = SolverConfig(timeout_ms=5000, memory_max_mb=None)
KEY = b"e2e-signing-key-0123456789abcdef"
ADAPTER = get_adapter("english-specialist")
JOINED_ID = "p1-q05"  # body 1 joins two halves of a dialogue line into one quotation (examples.md notes this, S12)


@pytest.fixture(scope="module")
def report() -> SpecialistReport:
    return fx.example1_report()


@pytest.fixture(scope="module")
def findings(report):
    return ADAPTER.structural_checks(report)


def run(name: str, rep: SpecialistReport, claim=None, **kw):
    claim = claim or fx.point_claim(rep)
    provider = FixtureTranslationProvider(fx.fixture_responses(name, claim))
    outcome = verify_claim(claim, rep, Translator(provider), structural=ADAPTER.structural_checks(rep), config=CFG,
                           signing_key=KEY, key_id="e2e", **kw)
    return outcome, provider


# (1) parsing and quotation grounding of Example 1 body 1


def test_example1_body1_is_parsed_into_petal_claims(report):
    assert report.original_response == fx.EXAMPLE1_BODY_1 and report.subject == "English A: Literature"
    point = fx.point_claim(report)
    assert point.claim_role == "point" and point.claim_text.startswith("García Márquez initially presents the administration of justice")
    roles = {c.claim_role for c in report.claims}
    assert roles == {"point", "evidence", "device", "interpretation", "link"}
    evidence = [c for c in report.claims if c.claim_role == "evidence"]
    assert [c.source_refs[0].excerpt for c in evidence] == [
        "thesis of homicide in legitimate defense of honor", "homicide", "legitimate defense", "legitimate",
        "We killed him openly, but we're innocent", "killed", "innocent", "openly", "Perhaps before God", "Before God and before men",
    ]
    assert all(c.source_refs[0].document_id == fx.DOCUMENT_ID for c in evidence)
    assert set(point.supporting_claim_ids) >= {c.claim_id for c in evidence}
    links = [c for c in report.claims if c.claim_role == "link"]
    assert [c.claim_text.split(",")[0] for c in links] == ["Effectively", "Ultimately"]


def test_example1_quotations_are_grounded_in_the_extract(report, findings):
    evidence = [c for c in report.claims if c.claim_role == "evidence"]
    verified = {c.claim_id: all(ch.verified for ch in check_claim_sources(c, report.supplied_texts)) for c in evidence}
    assert all(ok for cid, ok in verified.items() if cid != JOINED_ID), verified
    assert verified[JOINED_ID] is False  # the stitched dialogue line is not a verbatim span
    codes = [f.code for f in findings]
    assert "ES-SRC-001" not in codes
    assert codes == ["ES-SRC-005"] and findings[0].claim_ids == [JOINED_ID] and findings[0].severity == "warning"
    assert not [f for f in findings if f.severity == "error"]


def test_example1_whole_essay_segments_into_thesis_bodies_and_conclusion():
    rep = fx.example1_report(fx.EXAMPLE1_ESSAY, report_id="rep-ex1-essay")
    from epinoic_logic.adapters.english_specialist.parser import segment

    assert [p.kind for p in segment(fx.EXAMPLE1_ESSAY)] == ["thesis", "body", "body", "body", "conclusion"]
    assert len([c for c in rep.claims if c.claim_role == "point"]) == 3
    thesis = [c for c in rep.claims if c.claim_role == "thesis"]
    assert thesis and all(c.supporting_claim_ids == ["p2-point", "p3-point", "p4-point"] for c in thesis)
    findings = ADAPTER.structural_checks(rep)
    # Body 2 lowercases the first word of a sentence it quotes ("for the immense majority..."). The corpus marks it
    # found (case-only difference): a quotation-form warning (ES-SRC-006), never an invented-quotation error.
    assert not [f for f in findings if f.severity == "error"]
    form = [f for f in findings if f.code == "ES-SRC-006"]
    assert len(form) == 1 and form[0].severity == "warning" and "immense majority" in form[0].message
    assert "initial capital" in form[0].message and form[0].claim_ids == ["p3-q06"]


# (2) faithful chain


def test_faithful_chain_is_entailed_with_links_as_ungrounded_dependencies(report):
    outcome, provider = run("FAITHFUL_CHAIN", report)
    assert outcome.display_status is S.ENTAILED and outcome.translation.status is T.TRANSLATED
    v = outcome.verification
    assert v is not None and v.status is S.ENTAILED and verify_signature(v, KEY) and v.signature_key_id == "e2e"
    assert sorted(v.premises_relied_on) == ["E1", "E2", "L1", "L2", "L3"]
    assert sorted(v.ungrounded_dependencies) == ["L1", "L2", "L3"]
    assert all(c.verified is True for c in outcome.translation.grounding_checks if c.kind == "quotation")
    assert provider.served(fx.POINT_CLAIM_ID) == 1 and outcome.translation.provider.attempts == 1
    summary = outcome.summary
    assert summary.endswith(SCOPE_STATEMENT)
    assert "Ungrounded dependencies" in summary
    for link in ("L1", "L2", "L3"):
        assert f"{link} (specialist_inference, probable)" in summary
    assert "display status ENTAILED" in summary and "Structural findings" in summary


# (3) hallucinated quotation


def test_hallucinated_quotation_fails_grounding_and_is_flagged():
    rep = fx.example1_report(fx.EXAMPLE1_BODY_1_HALLUCINATED, report_id="rep-ex1-h")
    outcome, _ = run("HALLUCINATED_QUOTATION", rep)
    failed = [c for c in outcome.translation.grounding_checks if c.verified is False]
    assert [c.target_id for c in failed] == ["E2"] and failed[0].kind == "quotation"
    problem = outcome.translation.problem
    assert problem is not None and next(p for p in problem.premises if p.id == "E2").grounding.verified is False
    assert outcome.display_status is S.ENTAILED  # the encoding is entailed; the grounding is what fails
    assert "E2" in outcome.verification.ungrounded_dependencies and outcome.verification.ungrounded_dependencies
    src = [f for f in outcome.structural_findings if f.code == "ES-SRC-001"]
    assert len(src) == 1 and src[0].severity == "error" and fx.HALLUCINATED_EXCERPT in src[0].message
    summary = outcome.summary
    assert "Failed grounding checks" in summary and "E2" in summary and "grounding check failed" in summary
    assert "1 error(s)" in summary and "ES-SRC-001" in summary
    assert summary.endswith(SCOPE_STATEMENT)


# (4) contradiction


def test_contradiction_is_inconsistent_premises_naming_both(report):
    outcome, _ = run("CONTRADICTION", report)
    assert outcome.display_status is S.INCONSISTENT_PREMISES
    v = outcome.verification
    assert {"S1", "S2"} <= set(v.premises_relied_on) and v.unsat_core is not None and {"S1", "S2"} <= set(v.unsat_core.premise_ids)
    assert "S1" in outcome.summary and "S2" in outcome.summary and "contradict each other" in outcome.summary


# (5) non sequitur


def test_non_sequitur_is_a_counterexample(report):
    outcome, _ = run("NON_SEQUITUR", report)
    assert outcome.display_status is S.COUNTEREXAMPLE
    ce = outcome.verification.counterexample
    assert ce is not None
    values = {a.symbol: a.value for a in ce.assignments}
    assert values["p"] == "false" and values["q1"] == "true" and values["q2"] == "true"
    assert "Counterexample" in outcome.summary


# (6) standalone interpretation


def test_standalone_interpretation_is_not_eligible_and_never_reaches_the_provider(report):
    claim = next(c for c in report.claims if c.claim_role == "interpretation")
    provider = FixtureTranslationProvider({claim.claim_id: fx.FAITHFUL_CHAIN})  # would be wrong to use; must stay unused
    outcome = verify_claim(claim, report, Translator(provider), config=CFG)
    assert outcome.display_status is S.NOT_ELIGIBLE and outcome.display_status not in DEFINITIVE
    e = outcome.translation.eligibility
    assert e.eligible is False and e.eligibility_class.value == "NOT_ELIGIBLE_INTERPRETIVE" and e.route_to == "subject_evaluator"
    assert provider.served(claim.claim_id) == 0 and provider.calls == []
    assert outcome.translation.provider is None and outcome.verification is None
    assert "routed to subject_evaluator" in outcome.summary and outcome.summary.endswith(SCOPE_STATEMENT)


# (7) structural arithmetic


def test_structural_arith_is_entailed(report):
    rep, claim = fx.with_structural_claim(report)
    assert claim.claim_role == "structural" and claim.claim_id == fx.STRUCTURAL_CLAIM_ID
    outcome, _ = run("STRUCTURAL_ARITH", rep, claim)
    assert outcome.translation.eligibility.eligibility_class.value == "ARITHMETIC_CONSTRAINT"
    assert outcome.display_status is S.ENTAILED
    v = outcome.verification
    assert sorted(v.premises_relied_on) == ["STRANDS", "WORDS"] and v.ungrounded_dependencies == ["STRANDS"]
    assert fx.BODY_1_WORDS == 341 and fx.BODY_1_WORDS <= 400
    # a count over the limit is a COUNTEREXAMPLE, not a failure of the machinery
    over = {claim.claim_id: fx.structural_arith(claim.request_id, claim.claim_id, words=460)}
    outcome2 = verify_claim(claim, rep, Translator(FixtureTranslationProvider(over)), config=CFG)
    assert outcome2.display_status is S.COUNTEREXAMPLE


# (8) self-certification has no effect


def _with_self_certification(rep: SpecialistReport, claim_id: str) -> SpecialistReport:
    claims = [
        c if c.claim_id != claim_id else c.model_copy(update={"advisory_verification_eligibility": True, "advisory_verification_status": "verified"})
        for c in rep.claims
    ]
    return SpecialistReport.model_validate(rep.model_copy(update={"claims": claims}).model_dump(mode="json"))


@pytest.mark.parametrize("name", ["FAITHFUL_CHAIN", "NON_SEQUITUR", "CONTRADICTION"])
def test_self_certification_fields_do_not_change_the_display_status(report, name):
    plain, _ = run(name, report)
    certified_report = _with_self_certification(report, fx.POINT_CLAIM_ID)
    certified, _ = run(name, certified_report)
    assert certified.display_status is plain.display_status
    assert certified.translation.eligibility.eligibility_class is plain.translation.eligibility.eligibility_class
    assert any("advisory and was not used" in r for r in certified.translation.eligibility.reasons)


def test_self_certified_interpretation_stays_not_eligible(report):
    claim = next(c for c in report.claims if c.claim_role == "interpretation")
    certified_report = _with_self_certification(report, claim.claim_id)
    certified_claim = next(c for c in certified_report.claims if c.claim_id == claim.claim_id)
    assert certified_claim.advisory_verification_status == "verified"
    outcome = verify_claim(certified_claim, certified_report, Translator(FixtureTranslationProvider({})), config=CFG)
    assert outcome.display_status is S.NOT_ELIGIBLE


# (9) representation binding


def test_changed_label_changes_the_binding_digests():
    problem = Problem.model_validate(fx.FAITHFUL_CHAIN["problem"])
    relabelled = problem.model_copy(update={"conclusion": problem.conclusion.model_copy(update={"label": "a different gloss of the point"})})
    a, b = engine_verify(problem, CFG), engine_verify(relabelled, CFG)
    assert a.status is S.ENTAILED and b.status is S.ENTAILED
    assert a.binding.problem_digest != b.binding.problem_digest
    assert a.binding.binding_digest != b.binding.binding_digest
    assert a.binding.config_digest == b.binding.config_digest and a.binding.versions_digest == b.binding.versions_digest


def test_every_fixture_matches_its_declared_expected_status(report):
    for name, expected in fx.EXPECTED_STATUS.items():
        if name == "STRUCTURAL_ARITH":
            rep, claim = fx.with_structural_claim(report)
            outcome, _ = run(name, rep, claim)
        elif name == "HALLUCINATED_QUOTATION":
            outcome, _ = run(name, fx.example1_report(fx.EXAMPLE1_BODY_1_HALLUCINATED, report_id="rep-ex1-h2"))
        else:
            outcome, _ = run(name, report)
        assert outcome.display_status is expected, name
