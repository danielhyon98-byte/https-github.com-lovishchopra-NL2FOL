"""Translator oversight (``overseer/checks/translation.py``, OVS-TRN-001..007): every translation of a delivered claim is
re-checked from the JOURNAL as untrusted data, and the signed audit records it.

Model-proposed translations come from the translator's own pipeline (``Translator`` with the fixture provider, as the
arena drives it): the provider's JSON is parsed, validated, grounded and verified by the engine inside the channel call.
Faults the pipeline itself never produces (a translator bug, a compromised translator, a tampered outcome) are injected
by a ``transform`` applied to the outcome before the channel sees it, re-verified and re-composed so that only the fault
under test differs. Each case asserts the exact code, severity and claim, and a control.
"""
from __future__ import annotations

import copy
import json
from fractions import Fraction

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import verify
from epinoic_logic.ir.canonical import canonical_json
from epinoic_logic.ir.schema import Problem
from epinoic_logic.overseer import TranslationAudit
from epinoic_logic.overseer.audit import verify_audit
from epinoic_logic.overseer.checks import translation as T
from epinoic_logic.overseer.policy import may_act
from epinoic_logic.translate.contracts import EligibilityClass, EligibilityDecision, ProviderInfo, TranslationStatus, sha256_text
from epinoic_logic.translate.outcome import compose_outcome, verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider
from epinoic_logic.version import POLICY_VERSION

from .conftest import (CFG, DOC, EN_CLAIMS, EN_INPUT, EN_TEXT, KEY, english_report, make_auditor, make_plan, new_channel, withheld_as_circular_by_the_translator,
                       without_the_translators_circularity_gate)

POINT = "en-point"
SUPPORT = ["en-ev1", "en-ev2", "en-an"]


# ============================================================================================ building translations
def V(name: str) -> dict:
    return {"op": "var", "name": name}


def quoted(excerpt: str, doc: str = "doc-mill") -> dict:
    return {"kind": "quotation", "source_refs": [{"document_id": doc, "excerpt": excerpt}]}


INFER = {"kind": "specialist_inference"}


def genuine_problem(**over) -> dict:
    """The faithful encoding of en-point from the claims it cites: the two quotations, the specialist's inference, and
    the point as the conclusion (ENTAILED)."""
    p = {
        "problem_id": "p-en-point", "request_id": "req-ovs", "claim_id": POINT, "query": "entailment",
        "symbols": [
            {"name": "bell", "sort": "Bool", "meaning": "the foreman says work lasts until the bell", "grounding": quoted("We work until the bell")},
            {"name": "coal", "sort": "Bool", "meaning": "the children count the hours in coal", "grounding": quoted("counted every hour in coal")},
            {"name": "endless", "sort": "Bool", "meaning": "the writer presents work as endless", "grounding": INFER},
        ],
        "premises": [
            {"id": "P_bell", "expr": V("bell"), "label": "the bell line", "grounding": quoted("We work until the bell")},
            {"id": "P_coal", "expr": V("coal"), "label": "the coal line", "grounding": quoted("counted every hour in coal")},
            {"id": "P_link", "expr": {"op": "implies", "left": {"op": "and", "args": [V("bell"), V("coal")]}, "right": V("endless")},
             "label": "together the lines make work endless", "grounding": INFER},
        ],
        "conclusion": {"id": "C", "expr": V("endless"), "label": "the writer presents work as endless", "grounding": INFER},
    }
    p.update(over)
    return p


def proposal(problem: dict, *, flags=(), ambiguous: bool = False) -> str:
    return json.dumps({"problem": problem, "interpretation": {"reading": "the point follows from the two quotations", "glossary": [],
                                                                "ambiguity_flags": [dict(code=c, message=f"{c} reading") for c in flags]},
                       "ambiguous": ambiguous, "unsupported_reason": None})


def point_claims(**point_over) -> list[dict]:
    out = [dict(c) for c in EN_CLAIMS]
    out[0] = {**out[0], "supporting_claim_ids": list(SUPPORT), **point_over}
    return out


def run(responses: dict | None = None, *, transform=None, report=None, auditor=None, policy_version: str = POLICY_VERSION):
    """One request and one structured report on an observed channel; the report's eligible claims are translated by
    the pipeline from ``responses`` (claim id -> provider text) and verified by the engine inside the channel call."""
    aud = auditor or make_auditor(shadow="off")
    ch = new_channel(aud)
    responses = {POINT: proposal(genuine_problem())} if responses is None else responses
    translator = Translator(FixtureTranslationProvider(responses), policy_version=policy_version)

    def fn(claim, rep):
        if claim.claim_id not in responses:
            return None
        out = verify_claim(claim, rep, translator, config=CFG, signing_key=KEY, key_id="t")
        return transform(out, claim, rep) if transform is not None else out

    ch.channel.verify_claim_fn = fn
    m, _req, _rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _reply, rc = ch.respond(m.message_id, report or english_report(claims=point_claims()))
    assert rc.status is not TransmissionStatus.REJECTED  # delivered: its outcomes reached the router
    return aud, ch, rc


def recompose(out, claim, *, problem: dict | None = None, verification="keep", **tr_updates):
    """The outcome rebuilt around a changed translation (and, with ``problem``, a re-verified problem), so that its
    display status and summary are consistent and only the injected fault differs."""
    tr = out.translation
    ver = out.verification
    if problem is not None:
        p = Problem.model_validate(problem)
        tr_updates["problem"] = p
        ver = verify(p, CFG, signing_key=KEY, key_id="t")
    if verification != "keep":
        ver = verification
    tr2 = tr.model_copy(update=tr_updates)
    return compose_outcome(claim, tr2, ver, signing_key=KEY, key_id="t")


def trn(audit, code: str | None = None) -> list:
    return [f for f in audit.report.findings if f.code.startswith("OVS-TRN") and (code is None or f.code == code)]


def record(audit, claim_id: str = POINT) -> TranslationAudit:
    return next(r for r in audit.translations if r.claim_id == claim_id)


@pytest.fixture
def aud():
    a = make_auditor(shadow="off")
    yield a
    a.close()


# ============================================================================================ genuine translation
def test_a_faithful_model_proposed_translation_gives_no_trn_finding_and_is_recorded(aud):
    aud, ch, rc = run(auditor=aud)
    a = aud.audit(ch.uid)
    assert verify_audit(a, aud.keyring)
    assert trn(a) == []
    assert not [f for f in a.report.findings if f.severity == "error" and f.code != "OVS-DIV-001"]
    r = record(a)
    o = next(o for o in rc.outcomes if o.claim_id == POINT)
    assert r.model_proposed and r.provider_name == "fixture"
    assert r.translation_status == "TRANSLATED" and r.eligibility_class == "PROPOSITIONAL_ARGUMENT" and r.eligible
    assert r.claim_text == "The writer presents work as endless" and r.claim_text_sha256 == sha256_text(r.claim_text)
    assert r.cited_claim_ids == SUPPORT
    assert r.problem_json == canonical_json(o.translation.problem.model_dump(mode="json", exclude_none=True))
    assert r.problem_digest == o.verification.binding.problem_digest
    assert r.revalidation == "valid" and r.revalidation_detail == []
    assert r.result_id == o.verification.result_id and r.result_status == "ENTAILED" and r.signature_verified is True
    assert r.result_sha256 == aud.store.get(r.result_id).result_sha256
    assert r.display_status == "ENTAILED" and r.ambiguity_flags == [] and r.grounding_unverified == []
    assert r.checks_run == list(T.TRANSLATION_CHECKS) and r.codes == [] and r.outside_cited_claims == []
    assert a.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS")


def test_ineligible_claims_are_recorded_without_a_provider_and_their_eligibility_is_re_derived(aud):
    """Contained round c1 (rewritten to assert the reversed rule more strictly): the eligibility policy is deterministic
    and does not depend on who proposed the IR, so it is re-derived for every translation recorded under this code's
    policy version, a provider-less NOT_ELIGIBLE one included; here it agrees. With no problem there is nothing to trace."""
    report = english_report(claims=point_claims())
    responses = {POINT: proposal(genuine_problem()), "en-an": proposal(genuine_problem())}
    aud, ch, _rc = run(responses, auditor=aud, report=report)
    a = aud.audit(ch.uid)
    r = record(a, "en-an")
    assert r.translation_status == "NOT_ELIGIBLE" and not r.eligible and not r.model_proposed and r.problem_json is None
    assert r.revalidation == "no_problem" and "trace" not in r.checks_run and "eligibility" in r.checks_run and "status" in r.checks_run
    assert trn(a) == []  # the pipeline records no provider for a claim it ruled ineligible: never a fault


def test_the_translation_record_is_part_of_the_signed_audit(aud):
    aud, ch, _rc = run(auditor=aud)
    a = aud.audit(ch.uid)
    assert verify_audit(a, aud.keyring)
    for field, value in (("claim_text", "The writer presents work as finite"), ("problem_json", "{}"), ("result_status", "COUNTEREXAMPLE"),
                         ("codes", ["OVS-TRN-006"]), ("checks_run", [])):
        r = record(a).model_copy(update={field: value})
        forged = a.model_copy(update={"translations": [r if x.claim_id == POINT else x for x in a.translations]})
        assert not verify_audit(forged, aud.keyring), field


def test_translation_records_are_read_from_the_journal_not_the_live_objects(aud):
    aud, ch, rc = run(auditor=aud)
    o = next(o for o in rc.outcomes if o.claim_id == POINT)
    live_problem = o.translation.problem
    object.__setattr__(o.translation, "problem", Problem.model_validate(genuine_problem(premises=[])))  # a router-side edit of the live copy
    recs = [r for r in aud.translations(ch.uid) if r.claim_id == POINT]
    assert len(recs) == 1 and recs[0].problem_json == canonical_json(live_problem.model_dump(mode="json", exclude_none=True))
    assert recs[0].checks_run == T.TRANSLATION_CHECKS
    plain = [r for r in T.translation_records(aud.view(ch.uid), aud.store) if r.claim_id == POINT]
    assert len(plain) == 1 and plain[0].checks_run == () and plain[0].revalidation == "valid"


# ============================================================================================ TRN-001
def _nonlinear(out, claim, rep):
    p = genuine_problem(symbols=[{"name": "a", "sort": "Int"}, {"name": "b", "sort": "Int"}],
                        premises=[{"id": "P", "expr": {"op": "gt", "left": {"op": "mul", "args": [V("a"), V("b")]}, "right": {"op": "int", "value": "0"}}}],
                        conclusion={"id": "C", "expr": {"op": "gt", "left": V("a"), "right": {"op": "int", "value": "0"}}})
    return recompose(out, claim, problem=p)


def _other_claim(out, claim, rep):
    return recompose(out, claim, problem=genuine_problem(claim_id="en-ev1"))


def _too_deep(out, claim, rep):
    expr = V("endless")
    for _ in range(60):
        expr = {"op": "not", "arg": expr}
    return recompose(out, claim, problem=genuine_problem(conclusion={"id": "C", "expr": expr}))


@pytest.mark.parametrize("transform,why", [(_nonlinear, "only linear arithmetic"), (_other_claim, "claim 'en-ev1'"), (_too_deep, "depth")])
def test_trn001_an_ir_that_fails_revalidation_as_untrusted_data(aud, transform, why):
    aud, ch, rc = run(transform=transform, auditor=aud)
    a = aud.audit(ch.uid)
    f = trn(a, "OVS-TRN-001")
    assert len(f) == 1 and f[0].severity == "error" and f[0].claim_ids == [POINT] and rc.message_id in f[0].message_ids
    assert why.lower() in f[0].message.lower()
    assert record(a).revalidation == "invalid" and "OVS-TRN-001" in record(a).codes
    assert a.state == "AUDIT_FAILED"


def test_trn001_revalidate_reads_the_ir_as_json_never_as_code():
    claim = english_report(claims=point_claims()).claims[0]
    assert T.revalidate(None, claim) == ("no_problem", [])
    assert T.revalidate(canonical_json(genuine_problem()), claim) == ("valid", [])
    status, why = T.revalidate('{"__import__": "os", "problem_id": 1}', claim)
    assert status == "invalid" and why
    status, why = T.revalidate("not json at all", claim)
    assert status == "invalid" and why


# ============================================================================================ TRN-002
def test_trn002_ambiguity_flags_under_translated_is_an_ambiguity_resolved_silently(aud):
    flagged = proposal(genuine_problem(), flags=["SCOPE"])

    def resolve_silently(out, claim, rep):
        assert out.translation.status is TranslationStatus.AMBIGUOUS_TRANSLATION  # what the pipeline gave
        return recompose(out, claim, status=TranslationStatus.TRANSLATED)

    aud, ch, _rc = run({POINT: flagged}, transform=resolve_silently, auditor=aud)
    a = aud.audit(ch.uid)
    f = trn(a, "OVS-TRN-002")
    assert len(f) == 1 and f[0].severity == "error" and f[0].claim_ids == [POINT] and "silently" in f[0].message
    assert record(a).ambiguity_flags == ["SCOPE"]


def test_trn002_control_an_ambiguous_translation_kept_ambiguous(aud):
    aud, ch, rc = run({POINT: proposal(genuine_problem(), flags=["SCOPE"])}, auditor=aud)
    a = aud.audit(ch.uid)
    assert trn(a) == [] and record(a).translation_status == "AMBIGUOUS_TRANSLATION" and record(a).display_status == "AMBIGUOUS_TRANSLATION"


def test_trn002_a_claim_the_policy_rules_out_forced_into_ir(aud):
    """en-an is an interpretation (NOT_ELIGIBLE_INTERPRETIVE): the pipeline never calls a provider for it. A translator
    that forces it into IR anyway, recording an eligible class, is caught by re-deriving the policy decision."""
    forced_problem = genuine_problem(claim_id="en-an", problem_id="p-en-an")

    def force(out, claim, rep):
        assert out.translation.status is TranslationStatus.NOT_ELIGIBLE
        elig = EligibilityDecision(eligibility_class=EligibilityClass.PROPOSITIONAL_ARGUMENT, eligible=True, decided_by="deterministic", policy_version=POLICY_VERSION)
        return recompose(out, claim, problem=forced_problem, status=TranslationStatus.TRANSLATED, eligibility=elig,
                         provider=ProviderInfo(provider_name="fixture"))

    aud, ch, _rc = run({"en-an": "unused"}, transform=force, auditor=aud)
    a = aud.audit(ch.uid)
    f = trn(a, "OVS-TRN-002")
    assert len(f) == 1 and f[0].claim_ids == ["en-an"] and "NOT_ELIGIBLE_INTERPRETIVE" in f[0].message and "forced into IR" in f[0].message
    assert "eligibility" in record(a, "en-an").checks_run


def test_trn002_eligibility_is_not_rederived_under_another_policy_version(aud):
    """A model-proposed translation recorded under another policy version: the decision cannot be re-derived by this
    code, so the eligibility check does not run (and the record says so); the structural status checks still do, and
    (contained round c1, asserted in addition) a problem whose eligibility cannot be re-derived is itself TRN-002."""
    aud, ch, _rc = run(auditor=aud, policy_version="older-policy")
    a = aud.audit(ch.uid)
    r = record(a)
    assert r.model_proposed and r.policy_version == "older-policy" and "eligibility" not in r.checks_run and "status" in r.checks_run
    assert [f for f in trn(a, "OVS-TRN-002") if "older-policy" in f.message and "cannot be re-derived" in f.message]


@pytest.mark.parametrize("updates,words,rederived", [
    (dict(status=TranslationStatus.NOT_ELIGIBLE), "carries a problem", True),
    # the eligibility record names another policy version: it cannot be re-derived, and TRN-002 says so as well
    (dict(eligibility=EligibilityDecision(eligibility_class=EligibilityClass.NOT_ELIGIBLE_OTHER, eligible=False, decided_by="deterministic",
                                          policy_version="test")), "not eligible", False),
])
def test_trn002_status_or_eligibility_not_the_image_of_the_validation(aud, updates, words, rederived):
    """The provider removed as well (contained round c1; rewritten to assert the reversed rule more strictly): the
    eligibility re-derivation runs whoever proposed the IR, and a translation of the model pipeline that carries a problem
    without a provider is itself reported."""
    def tamper(out, claim, rep):
        return recompose(out, claim, provider=None, **updates)

    aud, ch, _rc = run(transform=tamper, auditor=aud)
    a = aud.audit(ch.uid)
    f = trn(a, "OVS-TRN-002")
    assert len(f) == 1 and f[0].claim_ids == [POINT] and words in f[0].message and "model-path translation without provider" in f[0].message
    assert not record(a).model_proposed and ("eligibility" in record(a).checks_run) is rederived and "trace" in record(a).checks_run
    assert rederived or "cannot be re-derived" in f[0].message


# ============================================================================================ TRN-003 / TRN-004
ABSENT = "We sleep until the whistle"


def test_trn003_a_grounding_marked_verified_that_the_rerun_does_not_verify(aud):
    p = genuine_problem()
    p["symbols"][0]["grounding"] = quoted(ABSENT)

    def overstate(out, claim, rep):
        tr = out.translation
        assert tr.grounding_checks and not all(c.verified for c in tr.grounding_checks)  # the pipeline reported it unverified
        prob = json.loads(canonical_json(tr.problem.model_dump(mode="json", exclude_none=True)))
        prob["symbols"][0]["grounding"]["verified"] = True
        checks = [c.model_copy(update={"verified": True}) for c in tr.grounding_checks]
        return recompose(out, claim, problem=prob, grounding_checks=checks)

    aud, ch, _rc = run({POINT: proposal(p)}, transform=overstate, auditor=aud)
    a = aud.audit(ch.uid)
    f = trn(a, "OVS-TRN-003")
    assert len(f) == 1 and f[0].severity == "error" and f[0].claim_ids == [POINT] and "bell is marked verified" in f[0].message
    assert "recorded as verified" in f[0].message
    assert a.state == "AUDIT_FAILED"


def test_trn004_a_quotation_excerpt_absent_from_the_named_supplied_text(aud):
    """The excerpt is the specialist's own words (in the response), cited as if it were in the extract: the pipeline
    reports it unverified, the auditor names it (a warning: the result relies on it only as an ungrounded dependency)."""
    p = genuine_problem()
    p["symbols"][2]["grounding"] = quoted("time itself is paid in fuel")
    aud, ch, _rc = run({POINT: proposal(p)}, auditor=aud)
    a = aud.audit(ch.uid)
    f = trn(a, "OVS-TRN-004")
    assert len(f) == 1 and f[0].severity == "warning" and f[0].claim_ids == [POINT] and f[0].document_ids == ["doc-mill"]
    assert trn(a, "OVS-TRN-005") == [] and trn(a, "OVS-TRN-003") == []  # the words are the specialist's: traced
    assert record(a).grounding_unverified == ["endless"]


def test_trn004_a_quotation_naming_a_document_that_is_not_supplied(aud):
    p = genuine_problem()
    p["premises"][0]["grounding"] = quoted("We work until the bell", doc="doc-elsewhere")
    aud, ch, _rc = run({POINT: proposal(p)}, auditor=aud)
    f = trn(aud.audit(ch.uid), "OVS-TRN-004")
    assert len(f) == 1 and f[0].document_ids == ["doc-elsewhere"]


# ============================================================================================ TRN-005
def test_trn005_an_invented_number(aud):
    p = genuine_problem(symbols=[{"name": "hours", "sort": "Int", "meaning": "hours of work"}],
                        premises=[{"id": "P_hours", "expr": {"op": "eq", "left": V("hours"), "right": {"op": "int", "value": "40"}},
                                   "grounding": {"kind": "arithmetic_fact"}}],
                        conclusion={"id": "C", "expr": {"op": "gt", "left": V("hours"), "right": {"op": "int", "value": "0"}}})
    aud, ch, _rc = run({POINT: proposal(p)}, auditor=aud)
    a = aud.audit(ch.uid)
    f = trn(a, "OVS-TRN-005")
    assert len(f) == 1 and f[0].severity == "warning" and f[0].claim_ids == [POINT] and "P_hours uses the number 40" in f[0].message
    assert "C uses" not in f[0].message  # 0 is structural
    # control: the same IR when the specialist states the number in words
    text = EN_TEXT + " They worked forty hours a week."
    aud2 = make_auditor(shadow="off")
    try:
        aud2, ch2, _ = run({POINT: proposal(p)}, auditor=aud2, report=english_report(text, claims=point_claims()))
        assert trn(aud2.audit(ch2.uid)) == []
    finally:
        aud2.close()


def test_trn005_an_invented_quotation(aud):
    p = genuine_problem()
    p["premises"][1]["grounding"] = quoted(ABSENT)
    aud, ch, _rc = run({POINT: proposal(p)}, auditor=aud)
    a = aud.audit(ch.uid)
    f5 = trn(a, "OVS-TRN-005")
    assert len(f5) == 1 and ABSENT in f5[0].message and f5[0].claim_ids == [POINT]
    assert len(trn(a, "OVS-TRN-004")) == 1  # and it is not in the extract it names


def test_trn005_a_supplied_text_quotation_the_specialist_did_not_quote_is_traced(aud):
    """Rule supplied-text: verbatim text of a supplied document is real text; whether using it is faithful is the
    overseer agents' question, never this check's."""
    p = genuine_problem()
    p["premises"][1]["grounding"] = quoted("the town grew rich on their silence")
    aud, ch, _rc = run({POINT: proposal(p)}, auditor=aud)
    a = aud.audit(ch.uid)
    assert trn(a) == []
    assert record(a).outside_cited_claims == ["P_coal"]  # recorded: outside the claim and the claims it cites


def test_trn005_runs_on_a_translation_whatever_proposed_it(aud):
    """Contained round c1 (rewritten to assert the reversed rule more strictly; it was "does not run on a translation no
    model proposed"): tracing is a deterministic comparison of the IR with the report, so a provider removed from a
    translation no longer hides an invented number, and the missing provider is reported too."""
    p = genuine_problem(symbols=[{"name": "hours", "sort": "Int"}],
                        premises=[{"id": "P_hours", "expr": {"op": "eq", "left": V("hours"), "right": {"op": "int", "value": "40"}}}],
                        conclusion={"id": "C", "expr": {"op": "gt", "left": V("hours"), "right": {"op": "int", "value": "0"}}})
    aud, ch, _rc = run({POINT: proposal(p)}, transform=lambda out, claim, rep: recompose(out, claim, provider=None), auditor=aud)
    a = aud.audit(ch.uid)
    f = trn(a, "OVS-TRN-005")
    assert len(f) == 1 and "40" in f[0].message and "trace" in record(a).checks_run and not record(a).model_proposed
    assert [x for x in trn(a, "OVS-TRN-002") if "model-path translation without provider" in x.message]


def test_a_declared_hand_built_translator_is_exempt_from_the_provider_rule_only(aud):
    """A translator the operator declared hand-built (``hand_built_translators``, recorded in the audit's coverage) may
    carry a problem with no provider; it is still traced and its eligibility re-derived when it is recorded under this
    code's policy version."""
    p = genuine_problem(symbols=[{"name": "hours", "sort": "Int"}],
                        premises=[{"id": "P_hours", "expr": {"op": "eq", "left": V("hours"), "right": {"op": "int", "value": "40"}}}],
                        conclusion={"id": "C", "expr": {"op": "gt", "left": V("hours"), "right": {"op": "int", "value": "0"}}})
    aud, ch, _rc = run({POINT: proposal(p)}, transform=lambda out, claim, rep: recompose(out, claim, provider=None, translator_version="test"), auditor=aud)
    a = aud.audit(ch.uid)
    assert "test" in (a.coverage.hand_built_translators or [])
    assert trn(a, "OVS-TRN-002") == [] and len(trn(a, "OVS-TRN-005")) == 1
    assert {"eligibility", "trace"} <= set(record(a).checks_run)


# ============================================================================================ TRN-006
def assumed_in_place_of_the_link(premise: dict) -> dict:
    """The point's encoding with the specialist's link (P_link) replaced by a premise carrying the conclusion: the result
    rests on the claim assumed (without P_assumed the two quotations do not give the point)."""
    p = genuine_problem()
    p["premises"] = [x for x in p["premises"] if x["id"] != "P_link"] + [{"id": "P_assumed", "expr": premise, "grounding": INFER}]
    return p


@pytest.mark.parametrize("premise", [V("endless"), {"op": "and", "args": [V("bell"), {"op": "and", "args": [V("coal"), V("endless")]}]}])
def test_trn006_a_conclusion_that_occurs_verbatim_among_the_premises(aud, premise, monkeypatch):
    """Rewritten after the round-7 simulation (rule ``restatement-necessity``; every original assertion kept): the
    restating premise now stands in for the specialist's link, so the auditor's own signed run without it is
    COUNTEREXAMPLE and the translation is circular. The earlier fixture appended the conclusion to the faithful encoding,
    whose other premises already give the point: that restatement is redundant, OVS-TRN-010 (a warning), pinned by
    ``test_trn010_a_restatement_the_other_premises_already_give_is_a_warning``.

    Rewritten again for the translator merge (rule ``circularity-agreement``, every assertion kept): the merged
    translator withholds this encoding itself (E112 at translation time), which is asserted first with no OVS-TRN
    finding; the overseer's TRN-006 is then asserted on the same encoding delivered past the translator's gate, where the
    engine's own E112 also withholds the displayed verdict."""
    p = assumed_in_place_of_the_link(premise)
    a0 = make_auditor(shadow="off")
    try:
        a0, ch0, rc0 = run({POINT: proposal(p)}, auditor=a0)
        o0 = next(o for o in rc0.outcomes if o.claim_id == POINT)
        assert withheld_as_circular_by_the_translator(o0)
        audit0 = a0.audit(ch0.uid)
        assert trn(audit0, "OVS-TRN-006") == [] and trn(audit0, "OVS-TRN-010") == [] and audit0.state != "AUDIT_FAILED"
        assert any("E112" in n and "circularity-agreement" in n for n in audit0.coverage.notes)
    finally:
        a0.close()
    without_the_translators_circularity_gate(monkeypatch)
    aud, ch, rc = run({POINT: proposal(p)}, auditor=aud)
    o = next(o for o in rc.outcomes if o.claim_id == POINT)
    assert o.verification.status.value == "ENTAILED"  # the engine is right about the encoding: it entails trivially
    # the engine's own rule agrees: the proof's core restates the conclusion from the writer's own premise (E112), so the
    # outcome layer displays no verdict
    assert "E112" in {d.code for d in o.verification.diagnostics} and o.display_status.value == "INVALID_FORMALIZATION"
    a = aud.audit(ch.uid)
    f = trn(a, "OVS-TRN-006")
    assert len(f) == 1 and f[0].severity == "error" and f[0].claim_ids == [POINT] and "P_assumed" in f[0].message
    assert f[0].formal_result_id == o.verification.result_id
    assert a.state == "AUDIT_FAILED" and "OVS-TRN-006" in record(a).codes
    # the evidence: the auditor's own run without the restating premise, signed under its run key and stored
    assert len(f[0].related_result_ids) == 1 and "COUNTEREXAMPLE" in f[0].message and trn(a, "OVS-TRN-010") == []
    run_rec = aud.store.get(f[0].related_result_ids[0])
    assert run_rec.origin == "auditor_run" and run_rec.key_id == "overseer-run" and run_rec.signature_ok_at_put and run_rec.status == "COUNTEREXAMPLE"
    assert f[0].related_result_ids[0] in a.report.formal_result_ids  # the audit lists the auditor's own runs it relied on
    assert "P_assumed" not in {x["id"] for x in json.loads(run_rec.problem_json)["premises"]}


def test_trn010_a_restatement_the_other_premises_already_give_is_a_warning(aud, monkeypatch):
    """Rule ``restatement-necessity`` (the round-7 bm-t13 shape on the synthetic task): the conclusion appended to the
    faithful encoding is a restatement the other premises already give. The auditor's own signed run without it is
    ENTAILED, so the translation is not circular: OVS-TRN-010, a warning naming the premise, which fails no transfer.

    Rewritten for the translator merge (rule ``circularity-agreement``, every assertion kept): the merged translator
    withholds this encoding itself (E112 at translation time, a redundant restatement included), asserted first with no
    OVS-TRN finding; TRN-010 is asserted on the encoding delivered past the translator's gate."""
    p = genuine_problem()
    p["premises"].append({"id": "P_assumed", "expr": V("endless"), "grounding": INFER})
    a0 = make_auditor(shadow="off")
    try:
        a0, ch0, rc0 = run({POINT: proposal(p)}, auditor=a0)
        assert withheld_as_circular_by_the_translator(next(o for o in rc0.outcomes if o.claim_id == POINT))
        audit0 = a0.audit(ch0.uid)
        assert trn(audit0, "OVS-TRN-006") == [] and trn(audit0, "OVS-TRN-010") == []
    finally:
        a0.close()
    without_the_translators_circularity_gate(monkeypatch)
    aud, ch, rc = run({POINT: proposal(p)}, auditor=aud)
    o = next(o for o in rc.outcomes if o.claim_id == POINT)
    a = aud.audit(ch.uid)
    assert trn(a, "OVS-TRN-006") == []
    f = trn(a, "OVS-TRN-010")
    assert len(f) == 1 and f[0].severity == "warning" and f[0].claim_ids == [POINT] and "P_assumed" in f[0].message
    assert f[0].formal_result_id == o.verification.result_id and "ENTAILED" in f[0].message
    run_rec = aud.store.get(f[0].related_result_ids[0])
    assert run_rec.origin == "auditor_run" and run_rec.signature_ok_at_put and run_rec.status == "ENTAILED"
    assert a.state == "AUDIT_PASSED_WITH_FINDINGS" and a.transfer_states[rc.message_id] == "AUDIT_PASSED_WITH_FINDINGS"
    assert record(a).codes == ["OVS-TRN-010"] and not [x for x in a.report.findings if x.severity == "error" and x.code != "OVS-DIV-001"]
    assert any("redundant restatement (OVS-TRN-010)" in n for n in a.coverage.notes)
    # the decision is memoised: a second audit cites the same signed run and adds no new one
    again = aud.audit(ch.uid)
    assert [x.related_result_ids for x in trn(again, "OVS-TRN-010")] == [f[0].related_result_ids]


def test_trn006_controls_an_implication_or_an_equivalent_but_different_premise_is_not_verbatim():
    p = genuine_problem()
    assert T.circular_premises(p) == []
    p["premises"].append({"id": "P_dn", "expr": {"op": "not", "arg": {"op": "not", "arg": V("endless")}}})
    assert T.circular_premises(p) == []  # logically equivalent, not verbatim: a meaning question for the agents
    p["premises"].append({"id": "P_same", "expr": json.loads(json.dumps(V("endless")))})
    assert T.circular_premises(p) == ["P_same"]
    assert T.circular_premises(None) == [] and T.circular_premises({"premises": []}) == [] and T.circular_premises({"conclusion": "x"}) == []


# ============================================================================================ TRN-007
def test_trn007_an_outcome_summary_that_is_not_the_statement_of_its_translation_and_signed_result(aud):
    def overclaim(out, claim, rep):
        return out.model_copy(update={"summary": "ENTAILED: the claim is proven true and needs no further review."})

    aud, ch, _rc = run(transform=overclaim, auditor=aud)
    a = aud.audit(ch.uid)
    f = trn(a, "OVS-TRN-007")
    assert len(f) == 1 and f[0].severity == "error" and f[0].claim_ids == [POINT]


def test_trn007_control_a_summary_composed_without_a_signing_key_is_a_configuration_the_composer_may_use(aud):
    aud, ch, _rc = run(transform=lambda out, claim, rep: compose_outcome(claim, out.translation, out.verification), auditor=aud)
    assert trn(aud.audit(ch.uid), "OVS-TRN-007") == []


# ============================================================================================ live operation
def test_live_a_circular_translation_holds_the_transfer_pending_then_fails_it_and_the_router_never_acts(monkeypatch):
    # rewritten after the round-7 simulation (every assertion kept): the restating premise stands in for the specialist's
    # link, so it is load-bearing (rule restatement-necessity); an appended, redundant one is OVS-TRN-010 and clears.
    # Rewritten for the translator merge (every assertion kept): the encoding is delivered past the merged translator's
    # circularity gate, which would withhold it itself (rule circularity-agreement; asserted in the TRN-006 test)
    without_the_translators_circularity_gate(monkeypatch)
    aud = make_auditor(shadow="off", eager=False)
    p = assumed_in_place_of_the_link(V("endless"))
    translator = Translator(FixtureTranslationProvider({POINT: proposal(p)}))

    def fn(claim, rep):
        return verify_claim(claim, rep, translator, config=CFG, signing_key=KEY, key_id="t") if claim.claim_id == POINT else None

    with RouterHub(signing_key=KEY, key_id="hub", verify_claim_fn=fn, config=CFG, auditor=aud) as hub:
        hub.open_task(make_plan())
        m, _req, _rq = hub.dispatch("task-ovs", "english-specialist", EN_INPUT, [DOC])
        _reply, rc = hub.receive("task-ovs", m.message_id, english_report(claims=point_claims()))
        first = hub.clearance("task-ovs", rc.message_id, receipt=rc)
        assert first.state == "AUDIT_PENDING" and not may_act(rc, first)
        assert any(p.startswith("l5|") for p in first.pending_result_ids)  # the translation checks have not run yet
        later = hub.clearance("task-ovs", rc.message_id, receipt=rc, wait_ms=250)
        assert later.state == "AUDIT_FAILED" and "OVS-TRN-006" in later.codes and not may_act(rc, later)
        final = hub.close_task("task-ovs")
        assert final.final and "OVS-TRN-006" in {f.code for f in final.report.findings} and record(final).codes == ["OVS-TRN-006"]
    aud.close()


def test_live_a_faithful_translation_clears_once_its_checks_have_run():
    aud = make_auditor(shadow="off", eager=False)
    translator = Translator(FixtureTranslationProvider({POINT: proposal(genuine_problem())}))

    def fn(claim, rep):
        return verify_claim(claim, rep, translator, config=CFG, signing_key=KEY, key_id="t") if claim.claim_id == POINT else None

    with RouterHub(signing_key=KEY, key_id="hub", verify_claim_fn=fn, config=CFG, auditor=aud) as hub:
        hub.open_task(make_plan())
        m, _req, _rq = hub.dispatch("task-ovs", "english-specialist", EN_INPUT, [DOC])
        _reply, rc = hub.receive("task-ovs", m.message_id, english_report(claims=point_claims()))
        clr = hub.clearance("task-ovs", rc.message_id, receipt=rc, wait_ms=250)
        assert clr.state in ("AUDIT_PASSED", "AUDIT_PASSED_WITH_FINDINGS") and not any(c.startswith("OVS-TRN") for c in clr.codes)
        assert may_act(rc, clr)
    aud.close()


def test_a_translation_check_that_fails_internally_fails_closed(aud, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("revalidation crashed")

    monkeypatch.setattr(T, "revalidate", boom)
    aud, ch, _rc = run(auditor=aud)
    a = aud.audit(ch.uid)
    f = [x for x in a.report.findings if x.code == "OVS-AUDIT-001"]
    assert f and any("translation" in x.message for x in f) and a.state == "AUDIT_FAILED"


def test_a_rejected_transfer_delivered_no_translation_and_is_not_checked(aud):
    ch = new_channel(aud)
    translator = Translator(FixtureTranslationProvider({POINT: proposal(genuine_problem(premises=[], conclusion={"id": "C", "expr": V("endless")}))}))
    ch.channel.verify_claim_fn = lambda claim, rep: verify_claim(claim, rep, translator, config=CFG, signing_key=KEY, key_id="t") if claim.claim_id == POINT else None
    m, _req, _rq = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    bad = english_report(claims=point_claims(), request_id="req-other")  # answers another request: REJECTED
    _reply, rc = ch.respond(m.message_id, bad)
    assert rc.status is TransmissionStatus.REJECTED
    assert aud.audit(ch.uid).translations == [] and aud.translations(ch.uid) == []


# ============================================================================================ the spelling rules (TRN-005)
@pytest.mark.parametrize("text,expected", [
    ("cut US exports by about two-thirds", {Fraction(2, 3), Fraction(3)}),
    ("roughly a tenth of its population", {Fraction(1, 10), Fraction(10)}),
    ("three quarters of the vote", {Fraction(3, 4)}),
    ("Parliament suspended habeas corpus in March 1817", {Fraction(3), Fraction(1817)}),
    ("signed on 28 Sept. 1919", {Fraction(9), Fraction(28), Fraction(1919)}),
    ("13 per cent of the territory", {Fraction(13), Fraction(13, 100), Fraction(100)}),
    ("twenty-one children and 9,000 banks", {Fraction(21), Fraction(9000)}),
    ("two hundred to adore", {Fraction(200)}),
])
def test_text_numbers_reads_the_named_spelling_rules(text, expected):
    assert expected <= T.text_numbers(text)


def test_text_numbers_never_reads_a_lowercase_modal_or_a_bare_word_as_a_month():
    assert Fraction(5) not in T.text_numbers("it may be so")
    assert Fraction(3) not in T.text_numbers("they march at dawn")


def test_number_traced_rules():
    known = T.text_numbers("about a tenth of 1902's output; 13 per cent")
    assert T.number_traced(Fraction(10), known)               # a tenth written as a percentage
    assert T.number_traced(Fraction(13, 100), known)          # a percentage written as a fraction
    assert T.number_traced(Fraction(19020531), known)         # date-encoding of a stated year
    assert not T.number_traced(Fraction(19021331), known)     # month 13 is no date
    assert not T.number_traced(Fraction(18991011), known)     # 1899 is not stated
    years = T.text_numbers("about a tenth of 1902's output")
    assert not T.number_traced(Fraction(10000), years)
    assert T.number_traced(Fraction(10000), years, date_encoded=True)  # the divisor that extracts the year
    assert T.number_traced(Fraction(0), set()) and T.number_traced(Fraction(-1), set())
    assert not T.number_traced(Fraction(40), known)


def test_untraced_content_sees_every_number_of_every_assertion_and_every_excerpt():
    p = genuine_problem(symbols=[{"name": "x", "sort": "Int", "grounding": quoted("not in any text")}],
                        premises=[{"id": "P", "expr": {"op": "eq", "left": V("x"), "right": {"op": "add", "args": [{"op": "int", "value": "7"},
                                                                                                                   {"op": "int", "value": "12"}]}}}],
                        conclusion={"id": "C", "expr": {"op": "gt", "left": V("x"), "right": {"op": "int", "value": "18"}}, "grounding": {"kind": "task_setting"}})
    prob = Problem.model_validate(p)
    out = T.untraced_content(prob, p, ["twelve hours"], ["more than 18 hours"], ["an extract"])
    assert ("x", "x quotes 'not in any text'") in out
    assert ("P", "P uses the number 7") in out and not any("number 12" in d for _n, d in out)
    assert not any(n == "C" for n, _d in out)  # a task-setting conclusion may take its number from the request
    out2 = T.untraced_content(prob, p, ["twelve hours"], [], ["an extract with not in any text inside"])
    assert ("x", "x quotes 'not in any text'") not in out2  # rule supplied-text
