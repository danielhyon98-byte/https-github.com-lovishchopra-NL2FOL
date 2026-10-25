"""The Overseer rebuilt on the STEM-merged translator: every named rule the merge needed, each pinned with a control.

The translator merge brings the STEM branches (claim ids ``s``/``m``/``c``, hub hooks, named engine policies), the
original translator's round-5 to round-7 fixes (English, History and generic parsers, the core pack's quotation rules,
the pipeline's circularity gate, E111/E112) and agent-qualified generic ids. Each rule below makes the Overseer read the
merged infrastructure as it is; each test pairs the merged behaviour with a control showing the check still fires:

* fidelity: ``mark-annotation`` (a mark allocation the parsers leave out of a claim is structure), ``same-form-figures``
  (FID-006 reads the claims' figures in the content's comparison form), ``no-quotation-to-verify`` (the core pack's own
  reading: words the request holds and a mentioned word are no quotation to verify), ``offered-check`` (the auditor's
  self-certification detector reads "I will check them" as an offer), ``carried-list-number`` after a colon;
* receipts: ``ambiguous-reading`` (INT-REQ-007 is an error except for an AMBIGUOUS_TRANSLATION), the relay rule
  re-derived with the channel's router identity (INT-ENV-007), ``merged-coverage`` (the coverage rule re-run with the
  branch's hub hooks);
* formal: ``merged-measure`` and ``range-bound`` (a word bound recounted as the merged channel measures it, one range
  problem for "about N words");
* results: ``policy-configs`` and ``policy-limits`` (a branch check run under a named engine policy), ``unsigned-probe``
  (the pipeline's own unsigned probe replayed under its own configuration);
* consolidation: ``duplicate-collision`` (only collisions with other answers to the same input leave a member clean);
* translation: ``circularity-agreement`` with ``grounded-transcription`` (the translator's classification, the
  review-round-1 number trace kept); the third repair's ``data-standing`` and ``same-quantity`` (decision 55, which
  withdrew the second repair's ``figure-transcription``: a task setting or supplied text with no excerpt is never a
  transcription, whatever numbers the request states; the request can only refute it), ``semantic-restatement`` (a
  restatement in another form: Boolean structure, the order of numbers, identity elements; never arithmetic) and
  ``receipt-disclosure`` (a writer's-own premise restating part of the conclusion, graded by what the receipt
  discloses).

No model is called; translations come from the translator's own pipeline with the fixture provider.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Optional

import pytest

from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.engine.policies import PACK_POLICIES, policy_config
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.integrity import AgentRole, IntegrityFinding, WorkPlan
from epinoic_logic.ir.schema import DEFAULT_LIMITS
from epinoic_logic.overseer.checks import receipts as RC
from epinoic_logic.overseer.checks.fidelity import _claim_figures, _strip_carried_numbers, no_quotation_to_verify, strip_mark_annotations
from epinoic_logic.overseer.checks.results import _allowed_configs, replay_config
from epinoic_logic.overseer.checks.selfcert import flags_self_certification
from epinoic_logic.overseer.replay import recorded_policy, replay_problem
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

from .conftest import (CFG, DOC, EN_CLAIMS, EN_INPUT, EN_TEXT, KEY, english_report, findings, make_auditor, make_plan, new_channel, ovs_errors,
                       withheld_as_circular_by_the_translator)
from .test_hook_hub import audited_hub
from .test_translation_oversight import INFER, POINT, V, genuine_problem, proposal, quoted, run, trn


@pytest.fixture
def aud():
    a = make_auditor(shadow="off")
    yield a
    a.close()


def _deliver_raw(subject: str, agent: str, task_type: str, docs: list, text: str, *, request: str = "Answer the question; quote exactly."):
    """One raw answer through an audited hub (the branch parser of ``subject`` parses it, as in the arena)."""
    hub = audited_hub(auditor=make_auditor(shadow="off"))
    try:
        hub.open_task(WorkPlan(plan_id="plan-t", request_id="req-t", task_id="t", subject=subject, task_type=task_type,
                               selected_agent_ids=[agent, "combinator"], allowed_document_ids=[d.document_id for d in docs]))
        m, _req, _rq = hub.dispatch("t", agent, request, docs)
        reply, rc = hub.receive("t", m.message_id, text, agent_id=agent, report_id="rep-t")
        return reply, rc, hub.audit("t")
    finally:
        hub.close()


# ============================================================================================ fidelity: mark-annotation
def test_rule_mark_annotation_removes_what_the_parsers_leave_out_of_a_claim():
    assert strip_mark_annotations("and only 9 [1]. Nymphs rise") == "and only 9. Nymphs rise"
    assert strip_mark_annotations("can be enforced [1 spare].") == "can be enforced."
    assert strip_mark_annotations("Total = 12 [2 marks]\nNext") == "Total = 12\nNext"
    assert strip_mark_annotations("$A = 4000(1.003)^{60}$ (M1)\n$= 4787.58$ (A1)\n") == "$A = 4000(1.003)^{60}$\n$= 4787.58$\n"
    assert strip_mark_annotations("x = 3  M1\nnext") == "x = 3\nnext"
    # control: an annotation-like token inside a sentence that goes on is kept; a figure in brackets that is no mark too
    assert strip_mark_annotations("the [1] reading continues") == "the [1] reading continues"
    assert strip_mark_annotations("site B (8.4 mg) holds most") == "site B (8.4 mg) holds most"


MARKED = ("(a) Percentage decrease = (9.6 - 3.8) / 9.6 x 100 = 60.4% decrease [1]\n\n"
          "(b) Nymph numbers fall as nitrate rises: site A has the least nitrate and the most nymphs (34), while site B has the most "
          "nitrate and only 9 [1]. The fit is not exact: C has less nitrate than B yet fewer nymphs [1 spare].")


def test_a_stem_answer_with_mark_allocations_is_never_fid_001_or_fid_006():
    reply, rc, audit = _deliver_raw("Environmental Systems and Societies", "ess-specialist", "data_based_question", [], MARKED)
    rep = SpecialistReport.model_validate(reply.payload)
    assert any(c.claim_text.endswith("only 9.") for c in rep.claims)  # the parser left the mark out of the claim
    assert not findings(audit, "OVS-FID-001") and not findings(audit, "OVS-FID-006"), [(f.code, f.message[:160]) for f in audit.report.findings]
    assert not ovs_errors(audit)


def test_control_a_claim_whose_words_differ_is_still_fid_001_when_the_marks_are_read_away(aud):
    text = EN_TEXT + " The bell ends the day [1]."
    claims = [*[dict(c) for c in EN_CLAIMS], dict(claim_id="en-x", claim_text="The bell starts the day.", claim_role="analysis", materiality="supporting")]
    ch = new_channel(aud)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _msg, rc = ch.respond(m.message_id, english_report(text, claims))
    f = findings(aud.audit(ch.uid), "OVS-FID-001")
    assert [x.claim_ids for x in f] == [["en-x"]]


# ============================================================================================ fidelity: same-form-figures
def test_rule_same_form_figures_a_minus_sign_and_a_superscript_power_are_carried(aud):
    text = EN_TEXT + " The balance is PV = −4000, and the flow is 1.2 mg dm⁻³."
    claims = [*[dict(c) for c in EN_CLAIMS], dict(claim_id="en-x", claim_text="The balance is PV = −4000, and the flow is 1.2 mg dm⁻³.",
                                                   claim_role="analysis", materiality="supporting")]
    ch = new_channel(aud)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    ch.respond(m.message_id, english_report(text, claims))
    assert not findings(aud.audit(ch.uid), "OVS-FID-006")


def test_control_a_figure_no_claim_carries_is_still_fid_006(aud):
    text = EN_TEXT + " The balance is PV = −4000, and the flow is 1.2 mg dm⁻³."
    ch = new_channel(aud)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    ch.respond(m.message_id, english_report(text))  # no claim carries the added sentence
    f = findings(aud.audit(ch.uid), "OVS-FID-006")
    assert f and "-4000" in f[0].message and f[0].severity == "warning"


# ============================================================================================ fidelity: no-quotation-to-verify
def test_rule_no_quotation_to_verify_reads_the_request_and_mentions_as_the_core_pack_does():
    from epinoic_logic.adapters.markdown import find_quotation_spans
    from epinoic_logic.branches.packs import _absent_mentions, _quote_key
    response = 'The comparison has no "like" or "as", so it is a metaphor; her "returning home" is rehearsed, and she says "never at rest".'
    mentions = {_quote_key(q) for q in _absent_mentions(response, find_quotation_spans(response))}
    assert mentions == {"like", "as"}
    request = "How does the writer present Mrs Okafor's feelings about returning home?"
    exempt = no_quotation_to_verify(["like", "returning home", "never at rest"], request, mentions)
    assert exempt == ["like", "returning home"]  # "never at rest" is a quotation to verify: neither in the request nor a mention
    assert no_quotation_to_verify(["returning home"], None, set()) == []  # no request text: nothing is located in it


#: The recorded round-7 lit-t13 shape (two supplied texts, so a quotation whose sentence names neither is credited to no
#: text): a phrase of the request ("returning home"), a mention of words the text lacks ('has no "like" or "as"') and an
#: invented quotation ("a silver hush of dread"), which the core pack names as unverifiable (CORE-SRC-003).
LIT = SuppliedText(document_id="doc-ferry", title="The Ferry", author="A. Writer",
                   text="She rehearsed three different first sentences and discarded each of them at a different station. "
                        "The bruise of the sky spread over the water.")
LIT_STUDENT = SuppliedText(document_id="doc-ferry-student", title="Student paragraph", author="student",
                           text="Mrs Okafor is nervous, which shows she is scared. The sky is a bruise.")
LIT_REQUEST = "How does the writer present Mrs Okafor's feelings about returning home? Comment on my paragraph and quote exactly."
LIT_TEXT = ('Add the evidence that answers "returning home" directly: she "rehearsed three different first sentences". '
            'Name the device accurately: the bruise comparison has no "like" or "as", so it is a metaphor. '
            'She feels "a silver hush of dread" on the crossing.')
#: The claims the merged English parser delivers that quote the request's phrase or the mentioned words (none of them is a
#: quotation to verify) and the claims that quote the invented words (p1-q05 its evidence claim, p1-s03 its sentence).
LIT_EXEMPT_CLAIMS = {"p1-point", "p1-q01", "p1-q03", "p1-q04", "p1-s02"}
LIT_INVENTED_CLAIMS = [["p1-q05"], ["p1-s03"]]


def _lit_task(aud, monkeypatch=None):
    if monkeypatch is not None:  # a channel that names nothing: the core pack's CORE-SRC-003 for the invented quotation dropped
        orig = TranslatorChannel._branch_checks

        def silent(self, report, req, fnd, *a, **kw):
            structural, results, ids = orig(self, report, req, fnd, *a, **kw)
            return [sf for sf in structural if sf.code != "CORE-SRC-003"], results, ids
        monkeypatch.setattr(TranslatorChannel, "_branch_checks", silent)
        orig_finish = TranslatorChannel._finish

        def finish(self, msg, direction, findings_, *a, structural=(), **kw):
            return orig_finish(self, msg, direction, findings_, *a, structural=[sf for sf in structural if sf.code != "CORE-SRC-003"], **kw)
        monkeypatch.setattr(TranslatorChannel, "_finish", finish)
        # since the round-7 core fix (r7 history hand-off 2) the channel also names an uncredited quotation found in no
        # supplied text with INT-REQ-003; a channel that names nothing names that neither
        monkeypatch.setattr(TranslatorChannel, "_uncredited_quotations", staticmethod(lambda *a, **kw: []))
    ch = new_channel(aud, make_plan(allowed_document_ids=["doc-ferry", "doc-ferry-student"]))
    m, _r, _q = ch.request("router", "english-specialist", LIT_REQUEST, [LIT, LIT_STUDENT])
    _msg, rc = ch.respond_text(m.message_id, LIT_TEXT, agent_id="english-specialist", report_id="rep-lit")  # the English parser reads it
    return ch, rc


def _lit_claims(aud, ch) -> dict[str, str]:
    t = next(x for x in aud.view(ch.uid).transfers if x.report is not None)
    return {c.claim_id: c.claim_text for c in t.report.claims}


def test_quoted_words_of_the_request_and_a_mentioned_word_are_never_fid_004(aud, monkeypatch):
    ch, rc = _lit_task(aud)
    claims = _lit_claims(aud, ch)
    assert claims["p1-q01"] == '"returning home"' and claims["p1-q03"] == '"like"' and claims["p1-q04"] == '"as"'
    assert LIT_EXEMPT_CLAIMS <= set(claims)
    # the channel's source rules name none of them (a quotation of the request, a mention), only the invented one (CORE-SRC-003)
    named = ({cid for sf in rc.structural_findings if "-SRC-" in sf.code for cid in sf.claim_ids}
             | {cid for f in rc.findings if f.code in ("INT-REQ-003", "INT-REQ-010", "INT-REQ-013") for cid in f.claim_ids})
    assert named == {"p1-q05", "p1-s03"}
    assert sorted(cid for sf in rc.structural_findings if sf.code == "CORE-SRC-003" for cid in sf.claim_ids) == ["p1-q05", "p1-s03"]
    f = findings(aud.audit(ch.uid), "OVS-FID-004")
    assert f == [], [(x.claim_ids, x.message) for x in f]
    # control on the same delivery: without the rule, each of those claims would be FID-004 (the round-7 false alarms)
    import epinoic_logic.overseer.checks.fidelity as FID
    monkeypatch.setattr(FID, "no_quotation_to_verify", lambda quotations, request_text, mention_keys: [])
    aud2 = make_auditor(shadow="off")
    try:
        ch2, _rc2 = _lit_task(aud2)
        f2 = findings(aud2.audit(ch2.uid), "OVS-FID-004")
        assert {cid for x in f2 for cid in x.claim_ids} == LIT_EXEMPT_CLAIMS
    finally:
        aud2.close()


def test_control_an_invented_quotation_no_finding_names_is_still_fid_004(aud, monkeypatch):
    ch, rc = _lit_task(aud, monkeypatch)
    assert not any(sf.code == "CORE-SRC-003" for sf in rc.structural_findings)
    assert not any(set(f.claim_ids) & {"p1-q05", "p1-s03"} for f in rc.findings)  # the receipt names the invented quotation nowhere
    f = findings(aud.audit(ch.uid), "OVS-FID-004")
    assert sorted(x.claim_ids for x in f) == LIT_INVENTED_CLAIMS
    assert all("a silver hush of dread" in x.message and x.severity == "error" for x in f)


# ============================================================================================ fidelity: offered-check, carried-list-number
@pytest.mark.parametrize("sentence", [
    "Send your answers, with any revised processed values or graph description, and I will check them against each criterion.",
    "We can verify your table once you send it.",
    "I shall confirm the band when the report is complete.",
])
def test_rule_offered_check_an_offer_to_check_the_reader_s_work_is_no_self_certification(sentence):
    assert not flags_self_certification(sentence)


@pytest.mark.parametrize("sentence", [
    "I checked every figure against the table.", "I have confirmed each of these dates against the timeline.", "We verified every figure.",
    "These figures will be accurate.",
])
def test_control_a_check_done_or_an_accuracy_claim_is_still_flagged(sentence):
    assert flags_self_certification(sentence)


def test_rule_carried_list_number_after_a_colon():
    claim = "The main causes of hyperinflation in 1923 were: 1. Reparations owed under the Treaty of Versailles"
    assert "1." not in _strip_carried_numbers(claim, {"1", "2", "3"})
    figures = {label for label, _keys in _claim_figures(claim, {"1", "2", "3"})}
    assert "1" not in figures and any("1923" in x for x in figures)
    # control: a number after a colon that the response does not use as a list marker is a figure the claim states
    assert "3." in _strip_carried_numbers("The answer is: 3. The rest follows.", {"1", "2"})
    assert any(label == "3" for label, _k in _claim_figures("The answer is: 3. The rest follows.", {"1", "2"}))


# ============================================================================================ receipts: ambiguous-reading
def _inconsistent(*, flags=()) -> str:
    p = genuine_problem()
    p["premises"].append({"id": "P_not_bell", "expr": {"op": "not", "arg": V("bell")}, "label": "the bell line denied", "grounding": INFER})
    return proposal(p, flags=flags)


@pytest.mark.parametrize("flags, severity, status", [((), "error", "TRANSLATED"), (("SCOPE",), "warning", "AMBIGUOUS_TRANSLATION")])
def test_rule_ambiguous_reading_int_req_007_at_the_channel_s_severity_is_no_rcpt_004(aud, flags, severity, status):
    aud, ch, rc = run({POINT: _inconsistent(flags=flags)}, auditor=aud)
    o = next(o for o in rc.outcomes if o.claim_id == POINT)
    assert o.translation.status.value == status and o.verification.status.value == "INCONSISTENT_PREMISES"
    assert [(f.code, f.severity) for f in rc.findings if f.code == "INT-REQ-007"] == [("INT-REQ-007", severity)]
    assert not [f for f in findings(aud.audit(ch.uid), "OVS-RCPT-004") if "INT-REQ-007" in f.message]


def test_control_int_req_007_lowered_to_a_warning_for_a_translated_claim_is_rcpt_004(aud, monkeypatch):
    def lowered(claim, out):
        return IntegrityFinding(code="INT-REQ-007", severity="warning", message=f"claim {claim.claim_id} rests on premises that contradict each other",
                                claim_ids=[claim.claim_id], formal_result_id=out.verification.result_id, deterministic=False)
    monkeypatch.setattr(TranslatorChannel, "_inconsistent_premises", staticmethod(lowered))
    aud, ch, rc = run({POINT: _inconsistent()}, auditor=aud)
    f = [x for x in findings(aud.audit(ch.uid), "OVS-RCPT-004") if "INT-REQ-007" in x.message]
    assert f and "ambiguous-reading" in f[0].message and "TRANSLATED" in f[0].message and f[0].severity == "error"


# ============================================================================================ receipts: the relay rule with the router identity
def _relay_task(aud):
    ch = new_channel(aud)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    reply, rc = ch.respond(m.message_id, english_report())
    return ch, SpecialistReport.model_validate(reply.payload)


def test_a_relay_by_a_party_asserting_the_router_role_is_rejected_and_its_receipt_agrees(aud):
    ch, rep = _relay_task(aud)
    _m, rr = ch.relay("rogue-router", AgentRole.ROUTER, "history-specialist", AgentRole.SPECIALIST, rep)
    assert rr.status is TransmissionStatus.REJECTED and any(f.code == "INT-ENV-007" and "router" in f.message for f in rr.findings)
    _m2, ok = ch.relay("router", AgentRole.ROUTER, "history-specialist", AgentRole.SPECIALIST, rep)  # control: the channel's own router
    assert ok.status is not TransmissionStatus.REJECTED and not any(f.code == "INT-ENV-007" for f in ok.findings)
    a = aud.audit(ch.uid)
    assert not [f for f in findings(a, "OVS-RCPT-004") if "INT-ENV-007" in f.message]
    assert not any("relay-party rule could not be re-run" in n for n in a.coverage.notes)


def test_a_relay_delivered_past_the_router_identity_rule_is_rcpt_004(aud, monkeypatch):
    orig = TranslatorChannel._relay_parties

    def blind(self, msg, from_role, to_agent_id, to_role, payload_obj):
        return [f for f in orig(self, msg, from_role, to_agent_id, to_role, payload_obj) if not (f.code == "INT-ENV-007" and "router of this channel" in f.message)]
    monkeypatch.setattr(TranslatorChannel, "_relay_parties", blind)
    ch, rep = _relay_task(aud)
    _m, rr = ch.relay("rogue-router", AgentRole.ROUTER, "history-specialist", AgentRole.SPECIALIST, rep)
    assert rr.status is not TransmissionStatus.REJECTED  # the channel let it through
    f = [x for x in findings(aud.audit(ch.uid), "OVS-RCPT-004") if "INT-ENV-007" in x.message]
    assert f and rr.message_id in f[0].message_ids


# ============================================================================================ receipts: merged-coverage
def test_rule_merged_coverage_reruns_the_coverage_rule_with_the_branch_s_hub_hooks(aud):
    from epinoic_logic.branches import default_registry

    from .test_corrections_stem_ready import physics_task
    ch, rcs = physics_task(aud)
    rc = rcs["rep-ph-1"]
    assert [(c.item_id, c.addressed) for c in rc.coverage] == [("i1", True)]
    view = aud.view(ch.uid)
    t = next(x for x in view.transfers if x.kind == "response" and x.report is not None and x.report.report_id == "rep-ph-1")
    req = view.by_seq[t.request_seq].request
    branch, profile = default_registry().for_subject("Physics")
    ns = SimpleNamespace(_hook=TranslatorChannel._hook)
    without = RC._CHANNEL_COVERAGE(ns, req, t.report, echoed=False, hooks=None, profile_key="")
    assert [(c.item_id, c.addressed) for c in without] == [("i1", False)]  # without the hooks the item would read unaddressed
    with_hooks = RC._CHANNEL_COVERAGE(ns, req, t.report, echoed=False, hooks=branch.hub_hooks, profile_key=profile.key)
    assert [(c.item_id, c.addressed, c.addressed_by_claim_ids) for c in with_hooks] == [(c.item_id, c.addressed, c.addressed_by_claim_ids) for c in rc.coverage]
    assert not [f for f in findings(aud.audit(ch.uid), "OVS-RCPT-004") if "coverage" in f.message.lower() or "INT-REQ-004" in f.message]


def test_control_a_channel_that_drops_the_hooks_from_its_coverage_is_rcpt_004(aud, monkeypatch):
    from .test_corrections_stem_ready import physics_task
    orig = TranslatorChannel._coverage

    def no_hooks(self, req, report, *, echoed=False, hooks=None, profile_key=""):
        return orig(self, req, report, echoed=echoed, hooks=None, profile_key="")
    monkeypatch.setattr(TranslatorChannel, "_coverage", no_hooks)
    ch, rcs = physics_task(aud)
    assert [(c.item_id, c.addressed) for c in rcs["rep-ph-1"].coverage] == [("i1", False)]
    f = findings(aud.audit(ch.uid), "OVS-RCPT-004")
    assert any(rcs["rep-ph-1"].message_id in x.message_ids for x in f)


# ============================================================================================ formal: request-quotation
#: A structured English answer whose evidence claim cites, as an excerpt of the extract, words of the request itself: the
#: merged channel counts it covered by the request (no INT-REQ-003, no branch -SRC-001 error), as the core pack does.
REQ_QUOTE_TEXT = EN_TEXT + ' The task asks how the writer "presents work".'
REQ_QUOTE_CLAIMS = [*[dict(c) for c in EN_CLAIMS], dict(claim_id="en-req", claim_text="presents work", claim_role="evidence", materiality="supporting",
                                                        source_refs=[dict(document_id="doc-mill", excerpt="presents work")])]


def _request_quote_task(aud, claims=REQ_QUOTE_CLAIMS, text=REQ_QUOTE_TEXT):
    ch = new_channel(aud)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _msg, rc = ch.respond(m.message_id, english_report(text, [dict(c) for c in claims]))
    return ch, rc


def test_rule_request_quotation_a_claim_quoting_the_request_is_covered_as_the_merged_channel_counts_it(aud, monkeypatch):
    from epinoic_logic.overseer.checks import formal as FORMAL
    ch, rc = _request_quote_task(aud)
    assert rc.status is TransmissionStatus.ACCEPTED and not rc.findings and not [sf for sf in rc.structural_findings if sf.severity == "error"]
    a = aud.audit(ch.uid)
    assert not findings(a, "OVS-RCPT-004") and a.state == "AUDIT_PASSED"
    view = aud.view(ch.uid)
    t = next(x for x in view.transfers if x.report is not None)
    assert FORMAL.request_quoted_claims(t.report, view.by_seq[t.request_seq].request) == {"en-req"}
    # the false alarms the rule removes: without it, R2 expects the branch packs' -SRC-001 errors the channel suppressed
    monkeypatch.setattr(FORMAL, "request_quoted_claims", lambda rep, req: set())
    aud2 = make_auditor(shadow="off")
    try:
        ch2, _rc2 = _request_quote_task(aud2)
        f = findings(aud2.audit(ch2.uid), "OVS-RCPT-004")
        assert f and all(x.claim_ids == ["en-req"] for x in f) and {"CORE-SRC-001", "ES-SRC-001"} <= {c for x in f for c in ("CORE-SRC-001", "ES-SRC-001") if c in x.message}
    finally:
        aud2.close()


def test_control_a_channel_that_drops_an_invented_excerpts_finding_is_still_rcpt_004(aud, monkeypatch):
    claims = [*[dict(c) for c in EN_CLAIMS], dict(claim_id="en-inv", claim_text="the river carried every secret", claim_role="evidence", materiality="supporting",
                                                  source_refs=[dict(document_id="doc-mill", excerpt="the river carried every secret")])]
    text = EN_TEXT + ' The extract says "the river carried every secret".'
    orig = TranslatorChannel._source_findings

    def lax(self, report, supplied, *, request_text=None):  # treats an invented excerpt as if the request held it
        covered, form_covered, out = orig(self, report, supplied, request_text=request_text)
        dropped = {cid for f in out if f.code == "INT-REQ-003" for cid in f.claim_ids}
        return covered, form_covered | dropped, [f for f in out if f.code != "INT-REQ-003"]
    monkeypatch.setattr(TranslatorChannel, "_source_findings", lax)
    ch, rc = _request_quote_task(aud, claims=claims, text=text)
    assert not any("en-inv" in f.claim_ids for f in rc.findings) and not any("en-inv" in sf.claim_ids and sf.severity == "error" for sf in rc.structural_findings)
    f = [x for x in findings(aud.audit(ch.uid), "OVS-RCPT-004") if "en-inv" in x.claim_ids]
    assert f and all(x.severity == "error" and x.message_ids == [rc.message_id] for x in f)


# ============================================================================================ formal: merged-measure
PH_BOUND_REQUEST = ("A car accelerates from rest at 2.0 m s^-2 for 5.0 s. Calculate its final speed. "
                    "Explain your answer in no more than 25 words, plus working.")
PH_BOUND_ANSWER = ("Working:\n$v = u + at$\n$v = 0 + 2.0 \\times 5.0$\n$v = 10$ m s$^{-1}$\n\n"
                   "The car starts from rest, so its final speed is the acceleration multiplied by the time, which is 10 m s^-1.")


def _physics_bound(auditor=None):
    hub = audited_hub(auditor=auditor or make_auditor(shadow="off"))
    hub.open_task(WorkPlan(plan_id="plan-pb", request_id="req-pb", task_id="tpb", subject="Physics", task_type="short_answer",
                           selected_agent_ids=["physics-specialist", "combinator"]))
    m, _req, _rq = hub.dispatch("tpb", "physics-specialist", PH_BOUND_REQUEST, [])
    _reply, rc = hub.receive("tpb", m.message_id, PH_BOUND_ANSWER, agent_id="physics-specialist", report_id="rep-pb")
    return hub, rc


def test_rule_merged_measure_recounts_a_stem_word_bound_as_the_merged_channel_measures_it():
    from epinoic_logic.branches import default_registry
    from epinoic_logic.channel.request_parser import count_answer_words, measure_answer_words
    hub, rc = _physics_bound()
    try:
        (cr,) = [c for c in rc.constraint_results if c.method == "formal"]
        assert "prose only" in cr.detail and "working" in cr.detail and cr.formal_status == "ENTAILED"
        branch, profile = default_registry().for_subject("Physics")
        view = lambda text: TranslatorChannel._hook(lambda: branch.hub_hooks.word_count_view(text, profile.key), text)  # noqa: E731
        merged = measure_answer_words(PH_BOUND_ANSWER, excludes=("working",), view=view)[0]
        assert f"measured {merged} words" in cr.detail
        assert count_answer_words(PH_BOUND_ANSWER)[0] != merged  # the pre-merge recount would compare another number
        a = hub.audit("tpb")
        assert not findings(a, "OVS-FORM-003") and not findings(a, "OVS-FORM-004") and not findings(a, "OVS-RES-007")
    finally:
        hub.close()


def test_rule_merged_measure_the_pre_merge_recount_would_be_a_false_form_003(monkeypatch):
    from epinoic_logic.channel.request_parser import count_answer_words
    from epinoic_logic.overseer.checks import formal as FORMAL
    monkeypatch.setattr(FORMAL, "measure_answer_words", lambda text, excludes=(), view=None: (*count_answer_words(text), 0))
    hub, rc = _physics_bound()
    try:
        f = findings(hub.audit("tpb"), "OVS-FORM-003")
        assert f and "MEASURED" in f[0].message and f[0].message_ids == [rc.message_id]
    finally:
        hub.close()


def test_control_a_word_bound_measured_without_the_requests_exclusion_is_form_003(monkeypatch):
    import epinoic_logic.channel.bus as bus
    from epinoic_logic.channel.request_parser import measure_answer_words
    monkeypatch.setattr(bus, "measure_answer_words", lambda text, excludes=(), view=None: measure_answer_words(text, excludes=(), view=view))
    hub, rc = _physics_bound()
    try:
        (cr,) = [c for c in rc.constraint_results if c.method == "formal"]
        assert "prose only: 0 words" in cr.detail  # the channel measured the working as prose
        f = findings(hub.audit("tpb"), "OVS-FORM-003")
        assert f and "MEASURED" in f[0].message and f[0].formal_result_id == cr.formal_result_id
    finally:
        hub.close()


# ============================================================================================ formal: range-bound
ABOUT_INPUT = "Analyse how the writer presents work in the extract. Use quotations from the extract. Write about 40 words."


def _about_task(aud):
    ch = new_channel(aud)
    m, _r, _q = ch.request("router", "english-specialist", ABOUT_INPUT, [DOC])
    _msg, rc = ch.respond(m.message_id, english_report(REQ_QUOTE_TEXT, [dict(c) for c in EN_CLAIMS]))
    return ch, rc


def test_rule_range_bound_one_range_problem_for_about_n_words_is_no_form_003(aud):
    from epinoic_logic.channel.request_parser import count_answer_words
    assert 36 <= count_answer_words(REQ_QUOTE_TEXT)[0] <= 44  # within "about 40 words" (36 to 44)
    ch, rc = _about_task(aud)
    words = [c for c in rc.constraint_results if c.method == "formal"]
    assert len(words) == 2 and len({c.formal_result_id for c in words}) == 1 and all(c.satisfied is True for c in words)
    view = aud.view(ch.uid)
    t = next(x for x in view.transfers if x.receipt is not None and x.receipt.message_id == rc.message_id)
    problem = json.loads(t.captured[words[0].formal_result_id].problem_json)
    assert problem["conclusion"]["expr"]["op"] == "and"  # one range problem both constraints cite
    a = aud.audit(ch.uid)
    assert not findings(a, "OVS-FORM-003") and not findings(a, "OVS-FORM-004") and not ovs_errors(a)


def test_control_a_range_problem_with_other_ends_is_form_003(aud, monkeypatch):
    orig = TranslatorChannel._formal_range

    def wider(self, req, low, high, measured):
        return orig(self, req, low.model_copy(update={"value": "10"}), high, measured)
    monkeypatch.setattr(TranslatorChannel, "_formal_range", wider)
    ch, rc = _about_task(aud)
    f = findings(aud.audit(ch.uid), "OVS-FORM-003")
    assert f and any("range" in x.message for x in f) and all(x.message_ids == [rc.message_id] for x in f)


def test_rule_range_bound_is_accepted_only_for_the_pair_the_span_states():
    from epinoic_logic.overseer.checks.formal import constraint_problem_mismatch
    ranged = {"premises": [{"id": "MEASURED", "expr": {"op": "eq", "left": V("n"), "right": {"op": "int", "value": "40"}}}],
              "conclusion": {"id": "BOUND", "expr": {"op": "and", "args": [{"op": "ge", "left": V("n"), "right": {"op": "int", "value": "36"}},
                                                                           {"op": "le", "left": V("n"), "right": {"op": "int", "value": "44"}}]}}}
    assert constraint_problem_mismatch(ranged, "ge", "36", 40, range_bounds=("36", "44")) == []
    assert constraint_problem_mismatch(ranged, "le", "44", 40, range_bounds=("36", "44")) == []
    # control: no range for this constraint (or another range) is a mismatch
    assert any("range" in w for w in constraint_problem_mismatch(ranged, "le", "44", 40))
    assert any("range" in w for w in constraint_problem_mismatch(ranged, "le", "44", 40, range_bounds=("30", "44")))


# ============================================================================================ results: policy-configs, policy-limits, unsigned-probe
MATHS_ALGEBRA = "$x^2 - 5x + 6 = 0 \\Rightarrow (x-2)(x-3) = 0$"


def _maths_algebra():
    hub = audited_hub(auditor=make_auditor(shadow="off"))
    hub.open_task(WorkPlan(plan_id="plan-ma", request_id="req-ma", task_id="tma", subject="Mathematics: Analysis and Approaches", task_type="short_answer",
                           selected_agent_ids=["maths-specialist", "combinator"]))
    m, _req, _rq = hub.dispatch("tma", "maths-specialist", "Factorise x^2 - 5x + 6.", [])
    _reply, rc = hub.receive("tma", m.message_id, MATHS_ALGEBRA, agent_id="maths-specialist", report_id="rep-ma")
    return hub, rc


def test_rule_policy_configs_a_nonlinear_stem_check_is_a_run_of_the_channels_engine():
    from epinoic_logic.engine.policies import NONLINEAR_LIMITS
    hub, rc = _maths_algebra()
    try:
        (fc,) = [c for c in rc.formal_checks if c.constraint_id.startswith("stem-alg")]
        assert fc.formal_status == "ENTAILED" and fc.satisfied is True
        view = hub.view("tma")
        res = hub.auditor.store.parsed(fc.formal_result_id)
        cfg = view.config_at(0)
        assert res.limits == NONLINEAR_LIMITS and res.solver_config == policy_config("nonlinear", cfg) and res.solver_config != cfg
        t = next(x for x in view.transfers if x.receipt is not None and x.receipt.message_id == rc.message_id)
        assert res.solver_config in _allowed_configs(view, t.seq) and replay_config(view, res, t.seq, "captured") == res.solver_config
        a = hub.audit("tma")
        assert not findings(a, "OVS-RES-004") and not findings(a, "OVS-AUDIT-005") and a.state == "AUDIT_PASSED"
        assert hub.auditor.replayer.drain(timeout_s=10) is not False
    finally:
        hub.close()


def test_control_without_the_policy_configs_the_nonlinear_check_would_be_res_004(monkeypatch):
    from epinoic_logic.overseer.checks import results as RESULTS

    def base_only(view, seq):  # the pre-merge rule: the journaled configuration, and the same with unsat cores
        info = view.info_at(seq) if view is not None else {}
        if not info.get("config"):
            return None
        cfg = view.config_at(seq)
        return [cfg, cfg.model_copy(update={"produce_unsat_core": True})]
    monkeypatch.setattr(RESULTS, "_allowed_configs", base_only)
    hub, rc = _maths_algebra()
    try:
        (fc,) = [c for c in rc.formal_checks if c.constraint_id.startswith("stem-alg")]
        f = [x for x in findings(hub.audit("tma"), "OVS-RES-004") if x.formal_result_id == fc.formal_result_id]
        assert f and "solver configuration" in f[0].message
    finally:
        hub.close()


def test_rule_policy_limits_replays_a_nonlinear_result_under_its_policy_and_only_a_named_policys_limits():
    from epinoic_logic.engine import verify
    from epinoic_logic.engine.policies import NONLINEAR_LIMITS
    from epinoic_logic.ir.canonical import canonical_json
    from epinoic_logic.ir.schema import Limits, Problem
    p = Problem.model_validate({
        "problem_id": "p-nl", "request_id": "req-nl", "claim_id": "m1.1", "query": "entailment",
        "symbols": [{"name": "x", "sort": "Real"}, {"name": "y", "sort": "Real"}],
        "premises": [{"id": "P1", "expr": {"op": "eq", "left": V("x"), "right": {"op": "real", "value": "2"}}, "grounding": {"kind": "task_setting"}},
                     {"id": "P2", "expr": {"op": "eq", "left": V("y"), "right": {"op": "real", "value": "3"}}, "grounding": {"kind": "task_setting"}}],
        "conclusion": {"id": "C", "expr": {"op": "eq", "left": {"op": "mul", "args": [V("x"), V("y")]}, "right": {"op": "real", "value": "6"}}},
    })
    cfg = policy_config("nonlinear", SolverConfig())
    res = verify(p, cfg, PACK_POLICIES["nonlinear"])
    assert res.status.value == "ENTAILED" and res.limits == NONLINEAR_LIMITS and recorded_policy(res) == "nonlinear"
    pj, cj = canonical_json(p.model_dump(mode="json", exclude_none=True)), canonical_json(cfg.model_dump(mode="json"))
    assert json.loads(replay_problem(pj, cj, "nonlinear"))["status"] == "ENTAILED"
    assert json.loads(replay_problem(pj, cj))["status"] == "UNSUPPORTED"  # under the default limits the replay could decide nothing
    # control: limits that are no named policy's are never trusted for a replay, nor the default policy's (recorded as none)
    assert recorded_policy(res.model_copy(update={"limits": Limits(allow_nonlinear=True, max_symbols=7)})) == ""
    assert recorded_policy(res.model_copy(update={"limits": DEFAULT_LIMITS})) == "" and recorded_policy(res.model_copy(update={"limits": None})) == ""


def test_rule_unsigned_probe_is_replayed_under_its_own_configuration_and_a_signed_result_never(aud):
    ch = new_channel(aud)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    _msg, rc = ch.respond(m.message_id, english_report())
    view = aud.view(ch.uid)
    t = next(x for x in view.transfers if x.receipt is not None and x.receipt.message_id == rc.message_id)
    res = aud.store.parsed(next(c.formal_result_id for c in rc.constraint_results if c.formal_result_id))
    assert res.signature  # the channel's own result is signed
    foreign = SolverConfig(timeout_ms=1234, memory_max_mb=None)
    probe = res.model_copy(update={"solver_config": foreign, "signature": None, "signature_key_id": None})
    assert replay_config(view, probe, t.seq, "captured") == foreign  # the translator's own probe, replayed as it ran
    # control: a SIGNED captured result naming that configuration is replayed under the channel's own, never its own
    assert replay_config(view, res.model_copy(update={"solver_config": foreign}), t.seq, "captured") == view.config_at(t.seq)


# ============================================================================================ consolidation: duplicate-collision
def test_control_a_collision_with_a_report_of_another_input_keeps_the_member_unclean():
    from .test_consolidation_consolidate import Dup
    hub = audited_hub()
    try:
        d = Dup(hub)
        other = EN_INPUT + " Keep it brief."
        assert d.answer("english-specialist", user_input=other, name="other-input").status.value == "ACCEPTED"
        rc = d.answer("english-1", name="first")  # its claim ids collide with the other input's answer only
        assert [(f.code, f.severity) for f in rc.findings] == [("INT-REQ-016", "warning")]
        r = d.consolidate(user_input_sha256=sha256_text(EN_INPUT))
        (g,) = r.groups
        assert [m.message_id for m in g.members] == [d.mids["first"]] and g.members[0].clean is False and not g.canonical_clean
        # the same collision with an answer to THIS input is the duplication the consolidation resolves (rule duplicate-collision)
        rc2 = d.answer("english-2", name="second")
        assert [(f.code, f.severity) for f in rc2.findings] == [("INT-REQ-016", "warning")]
        r2 = d.consolidate(user_input_sha256=sha256_text(EN_INPUT))
        (g2,) = r2.groups
        assert [m.clean for m in g2.members] == [False, False]  # both still collide with the other input's report
    finally:
        hub.close()


# ============================================================================================ translation: circularity-agreement
def _restating(kind: str, *, verified=None, value: str = "12", excerpt: Optional[str] = None, document_id: Optional[str] = None) -> dict:
    """``hours = 12`` given, and the claim ``hours = <value>`` also asserted by a premise grounded ``kind``."""
    g: dict = {"kind": kind}
    if verified is not None:
        g["verified"] = verified
    if excerpt is not None:
        g["source_refs"] = [{"document_id": document_id or "doc-mill", "excerpt": excerpt}]
    concl = {"op": "eq", "left": V("hours"), "right": {"op": "int", "value": value}}
    return {"problem_id": "p-rs", "request_id": "req-ovs", "claim_id": "en-point", "query": "entailment",
            "symbols": [{"name": "hours", "sort": "Int", "meaning": "the hours the claim states"}],
            "premises": [{"id": "P_restated", "expr": concl, "label": "the claim restated", "grounding": g}],
            "conclusion": {"id": "C", "expr": concl, "label": "the claim"}}


#: A supplied text that states the restated figure, so a grounding whose excerpt names it is VERIFIED by the deterministic
#: grounding check (an excerpt located in the named document that states the premise's figures).
HOURS_DOC = SuppliedText(document_id="doc-hours", title="Mill hours", author="Anonymous", text="In 1830 the children worked 12 hours a day in the mill.")
LOCATED = {"excerpt": "worked 12 hours a day", "document_id": "doc-hours"}


@pytest.mark.parametrize("kind, extra, own, withheld, standing", [
    # the writer's own for the translator too: the translator withholds the encoding (E112), and the overseer agrees
    ("assumption", {}, True, True, "own_kind"), ("specialist_inference", {}, True, True, "own_kind"), ("general_knowledge", {}, True, True, "own_kind"),
    # an arithmetic fact with no excerpt. Rewritten by the second translator merge (decision 73): the merged translator
    # validates it by its task-authority rule (the supplied text states 12 hours) and delivers it, where it had withheld it;
    # the overseer still reads it as the writer's own (no located excerpt: decision 55), stricter than the translator
    ("arithmetic_fact", {}, True, False, "own_kind"),
    ("quotation", {"excerpt": "worked twelve hours"}, True, True, "refuted"),  # a quotation the check does not verify
    # a kind LABEL with no located excerpt: the translator delivers the restatement on the label alone; the overseer reads
    # it as the writer's own (rule grounded-transcription, restored by the repair: a label is IR data, not evidence)
    ("rubric_rule", {}, True, False, "uncheckable"), ("knowledge_document", {}, True, False, "uncheckable"),
    ("library_source", {}, True, False, "uncheckable"), ("supplied_text", {}, True, False, "uncheckable"),
    # a source no check verifies a premise against stays the writer's own for the overseer even with a located excerpt
    ("rubric_rule", LOCATED, True, False, "uncheckable"), ("knowledge_document", LOCATED, True, False, "uncheckable"),
    ("library_source", LOCATED, True, False, "uncheckable"),
    # evidence the overseer re-derives: a verified excerpt stating the figure
    ("supplied_text", LOCATED, False, False, "transcription"), ("quotation", LOCATED, False, False, "transcription"),
    ("arithmetic_fact", LOCATED, False, False, "transcription"), ("task_setting", LOCATED, False, False, "transcription"),
    # a task setting with no excerpt whose figure the request states (rule same-quantity, the third repair, decision 55):
    # never a transcription (a number match is no evidence; rule figure-transcription is withdrawn), and the request,
    # which states 12 hours for the hours the premise's symbol names, does not refute it: undecided, the writer's own
    ("task_setting", {}, True, False, "undecided"),
])
def test_rule_circularity_agreement_the_overseer_is_never_looser_than_the_translator_and_takes_no_kind_label_as_evidence(kind, extra, own, withheld, standing):
    """Rules ``circularity-agreement`` and ``grounded-transcription`` (the repair of the translator merge, design decision
    49). Rewritten from ``test_rule_circularity_agreement_the_overseer_reads_a_restatement_as_the_translator_does``, which
    pinned the fault the independent test of the staged rebuild found: it asserted that a restatement grounded
    ``rubric_rule``, ``knowledge_document``, ``library_source`` or ``supplied_text`` with no source and nothing verified
    is a transcription, because the translator's rule delivers it on the kind label alone. Every withheld kind is still
    asserted to be the writer's own for the overseer, with the translator's gate agreeing (the same assertions); the four
    label-only kinds are now asserted to be the writer's own (stricter), and the evidence that does make a transcription
    is pinned with its controls. The third repair (decision 55) makes a ``task_setting`` with no excerpt the writer's own
    too (it had asserted a transcription: rule figure-transcription, withdrawn), and pins every case's standing (rule
    ``data-standing``)."""
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.overseer.checks.translation import restatement
    from epinoic_logic.translate.grounding import check_problem_grounding
    from epinoic_logic.translate.pipeline import Translator, _Rejected
    text = "The children worked 12 hours a day."
    rep = english_report(EN_TEXT + " " + text, [*[dict(c) for c in EN_CLAIMS], dict(claim_id="en-hours", claim_text=text[:-1], claim_role="point", materiality="material")],
                         docs=(DOC, HOURS_DOC))
    request = ["Write about the hours: 12 hours a day."]
    prob = Problem.model_validate(_restating(kind, **extra))
    rs = restatement(prob, rep, request)
    assert rs.named == ("P_restated",) and rs.holds is own
    assert (rs.own, rs.grounded) == ((("P_restated",), ()) if own else ((), ("P_restated",)))
    assert rs.standings == (("P_restated", standing),)
    assert rs.shown == (("P_restated",) if standing in ("own_kind", "refuted", "uncheckable") else ())
    assert rs.undecided == (("P_restated",) if standing == "undecided" else ())
    assert [pid for pid, _why in rs.why_own] == list(rs.own) and all(why for _pid, why in rs.why_own)

    def gate(problem: Problem) -> bool:
        """The translator's own gate, applied as its pipeline applies it (to the problem re-grounded by the deterministic
        grounding check on the report's supplied texts)."""
        grounded, _checks = check_problem_grounding(problem, list(rep.supplied_texts))
        try:
            Translator._circularity(grounded, "t")
            return False
        except _Rejected as exc:
            return exc.status.value == "INVALID_FORMALIZATION" and any("E112" in d for d in exc.diagnostics)
    assert gate(prob) is withheld and rs.translator_holds is withheld
    assert own or not withheld  # never looser than the translator: whatever it withholds, the overseer reads as circular
    # a grounding proposed as verified is re-derived by both (the IR's own flag is never trusted): the same decisions
    proposed_verified = Problem.model_validate(_restating(kind, verified=True, **extra))
    rs_v = restatement(proposed_verified, rep, request)
    assert gate(proposed_verified) is withheld and rs_v.holds is own and rs_v.standings == rs.standings
    if own and not withheld:
        # the reason names why no check upholds the grounding: no located excerpt, or a source no check verifies against
        (why,) = [w for _p, w in rs.why_own]
        assert ("no deterministic check verifies" in why) if kind in ("rubric_rule", "knowledge_document", "library_source") else ("not verified" in why), why


def test_control_a_located_excerpt_that_does_not_state_the_figure_is_no_evidence():
    """A ``supplied_text`` excerpt located in the document but not stating the restated figure is refuted by the grounding
    check (``figures_in_excerpt``), so the restatement is the writer's own for the translator and the overseer alike."""
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.overseer.checks.translation import restatement
    text = "The children worked 12 hours a day."
    rep = english_report(EN_TEXT + " " + text, docs=(DOC, HOURS_DOC))
    rs = restatement(Problem.model_validate(_restating("supplied_text", excerpt="the children worked", document_id="doc-hours")), rep, [])
    assert rs.holds is True and rs.translator_holds is True and "refutes" in rs.why_own[0][1]


LABEL_ONLY_KINDS = ("supplied_text", "rubric_rule", "knowledge_document", "library_source")


def _restated_by_label(kind: str, *, keep_link: bool = False, grounding: Optional[dict] = None) -> dict:
    """The point's encoding with the specialist's link replaced by (or, with ``keep_link``, joined by) a premise restating
    the conclusion under ``grounding`` (default: the kind label ``kind`` alone, no source, nothing verified)."""
    p = genuine_problem()
    if not keep_link:
        p["premises"] = [x for x in p["premises"] if x["id"] != "P_link"]
    p["premises"].append({"id": "P_assumed", "expr": V("endless"), "label": "the writer presents work as endless", "grounding": grounding or {"kind": kind}})
    return p


@pytest.mark.parametrize("kind", LABEL_ONLY_KINDS)
def test_a_load_bearing_restatement_grounded_by_a_kind_label_alone_is_delivered_entailed_and_is_trn_006(kind):
    """The independent test's case (the repair of the translator merge, decision 49): the merged translator's rule reads a
    restating premise grounded ``supplied_text``, ``rubric_rule``, ``knowledge_document`` or ``library_source`` as a
    transcription on the label alone, so it DELIVERS the circular encoding, the engine finds it ENTAILED with no E112, and
    the router is shown ENTAILED. The overseer upholds no such grounding (no located excerpt; no check verifies a premise
    against a rubric, knowledge document or library source): OVS-TRN-006, an error citing the auditor's signed run
    (COUNTEREXAMPLE without the premise), and the transfer fails: a non-success is never cleared as a success."""
    from epinoic_logic.overseer.policy import may_act
    aud = make_auditor(shadow="off")
    try:
        aud, ch, rc = run({POINT: proposal(_restated_by_label(kind))}, auditor=aud)
        o = next(x for x in rc.outcomes if x.claim_id == POINT)
        # the translator delivered it as a success: no gate, no engine E112
        assert o.translation.status.value == "TRANSLATED" and o.translation.problem is not None and not withheld_as_circular_by_the_translator(o)
        assert o.verification.status.value == "ENTAILED" and "E112" not in {d.code for d in o.verification.diagnostics}
        assert o.display_status.value == "ENTAILED"
        a = aud.audit(ch.uid)
        f = trn(a, "OVS-TRN-006")
        assert len(f) == 1 and f[0].severity == "error" and f[0].claim_ids == [POINT] and "P_assumed" in f[0].message
        assert "grounded-transcription" in f[0].message and kind in f[0].message and "COUNTEREXAMPLE" in f[0].message
        assert trn(a, "OVS-TRN-010") == []
        run_rec = aud.store.get(f[0].related_result_ids[0])
        assert run_rec.origin == "auditor_run" and run_rec.signature_ok_at_put and run_rec.status == "COUNTEREXAMPLE"
        assert a.transfer_states[rc.message_id] == "AUDIT_FAILED"
        clr = aud.clearance(ch.uid, rc.message_id, receipt=rc)
        assert clr.state == "AUDIT_FAILED" and "OVS-TRN-006" in clr.codes and not may_act(rc, clr)
    finally:
        aud.close()


@pytest.mark.parametrize("kind", LABEL_ONLY_KINDS)
def test_a_redundant_restatement_grounded_by_a_kind_label_alone_is_trn_010(kind):
    """Rule restatement-necessity grades the label-only restatement like any other writer's-own premise: beside the
    specialist's link the other premises still give the point, so it is OVS-TRN-010, a warning, and fails no transfer."""
    aud = make_auditor(shadow="off")
    try:
        aud, ch, rc = run({POINT: proposal(_restated_by_label(kind, keep_link=True))}, auditor=aud)
        a = aud.audit(ch.uid)
        f = trn(a, "OVS-TRN-010")
        assert trn(a, "OVS-TRN-006") == [] and len(f) == 1 and f[0].severity == "warning" and "P_assumed" in f[0].message
        assert a.transfer_states[rc.message_id] == "AUDIT_PASSED_WITH_FINDINGS"
    finally:
        aud.close()


def test_control_a_restatement_whose_excerpt_the_check_locates_is_a_transcription_with_no_finding():
    """Control: the same load-bearing restatement grounded ``supplied_text`` with an excerpt the deterministic check
    locates in the named document is a transcription check (rule grounded-transcription): no OVS-TRN-006 or -010, a
    coverage note; and the same excerpt under ``knowledge_document`` is still the writer's own (OVS-TRN-006)."""
    located = {"kind": "supplied_text", "source_refs": [{"document_id": "doc-mill", "excerpt": "We work until the bell"}]}
    aud = make_auditor(shadow="off")
    try:
        aud, ch, rc = run({POINT: proposal(_restated_by_label("supplied_text", grounding=located))}, auditor=aud)
        a = aud.audit(ch.uid)
        assert trn(a, "OVS-TRN-006") == [] and trn(a, "OVS-TRN-010") == []
        assert any("transcribes a grounded fact" in n and "P_assumed" in n for n in a.coverage.notes)
    finally:
        aud.close()
    aud2 = make_auditor(shadow="off")
    try:
        kd = {**located, "kind": "knowledge_document"}
        aud2, ch2, _rc2 = run({POINT: proposal(_restated_by_label("knowledge_document", grounding=kd))}, auditor=aud2)
        assert [x.claim_ids for x in trn(aud2.audit(ch2.uid), "OVS-TRN-006")] == [[POINT]]
    finally:
        aud2.close()


def test_control_a_conclusion_restated_only_in_part_is_its_evidence_not_a_restatement():
    """A conjunctive conclusion one of whose conjuncts the other premises derive is not restated as a whole: the premises
    stating its other conjuncts are its evidence (a verified quotation, or the writer's own premise alike). Neither the
    translator's rule (every conjunct) nor the verbatim reading holds, so there is no finding and no transcription note."""
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.overseer.checks.translation import restatement
    p = genuine_problem()
    p["conclusion"] = {"id": "C", "expr": {"op": "and", "args": [V("bell"), V("endless")]}, "label": "the bell line, and work endless"}
    rep = english_report(claims=[dict(c) for c in EN_CLAIMS])
    assert restatement(Problem.model_validate(p), rep, []) == restatement(None, rep)  # nothing restated
    p_own = json.loads(json.dumps(p))
    p_own["premises"].append({"id": "P_bell_again", "expr": V("bell"), "grounding": INFER})  # the writer's own, but endless is still derived
    rs = restatement(Problem.model_validate(p_own), rep, [])
    assert rs.holds is False and rs.own == () and rs.grounded == ()
    aud = make_auditor(shadow="off")
    try:
        aud, ch, _rc = run({POINT: proposal(p_own)}, auditor=aud)
        a = aud.audit(ch.uid)
        assert trn(a, "OVS-TRN-006") == [] and trn(a, "OVS-TRN-010") == []
        assert not any("transcribes a grounded fact" in n or "restate the conclusion" in n for n in a.coverage.notes)
    finally:
        aud.close()


def test_rule_grounded_transcription_number_trace_is_kept_on_top_of_the_translators_rule():
    """A task setting whose figure neither the request nor the report states is not traced to its source: the overseer
    reads it as the writer's own (review round 1, kept), although the translator's rule would deliver it; a check SHOWS
    it is not data (rule ``same-quantity``: the figure is stated nowhere in the request). Control: when the request states
    15 hours, the premise (no excerpt) is still the writer's own, since a number match is no evidence (the third repair,
    decision 55; it had asserted a transcription), but no check refutes it: undecided, not shown."""
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.overseer.checks.translation import restatement
    rep = english_report()
    prob = Problem.model_validate(_restating("task_setting", value="15"))
    rs = restatement(prob, rep, ["Write about the mill."])
    assert rs.holds is True and rs.standings == (("P_restated", "refuted"),) and rs.shown == ("P_restated",)
    assert "stated nowhere in the request" in dict(rs.why_own)["P_restated"]
    stated = restatement(prob, rep, ["Write about the mill: 15 hours a day."])  # control: the request states it
    assert stated.holds is True and stated.standings == (("P_restated", "undecided"),) and stated.shown == () and stated.undecided == ("P_restated",)
    assert "a number match is no evidence" in dict(stated.why_own)["P_restated"]


# ============================================================================================ translation: the second repair (decision 51)
from epinoic_logic.ir.schema import Problem  # noqa: E402
from epinoic_logic.overseer.checks.translation import RESTATEMENT_WAYS, restatement  # noqa: E402

#: A text supplied with the request (not quoted by the report) that states the restated figure.
ROTA_DOC = SuppliedText(document_id="doc-rota", title="Rota", author="Mill office", text="Rota of 1830: the children's shift ran 12 hours.")


def _numeric_restating(kind: str, *, refs: Optional[list[str]] = None, value: str = "12") -> dict:
    """``hours = <value>`` (an Int symbol) restated by a premise grounded ``kind`` with no excerpt; ``refs`` are the
    documents its source references name (no excerpt in any)."""
    g: dict = {"kind": kind}
    if refs is not None:
        g["source_refs"] = [{"document_id": d} for d in refs]
    concl = {"op": "eq", "left": V("hours"), "right": {"op": "int", "value": value}}
    return {"problem_id": "p-fig", "request_id": "req-ovs", "claim_id": "en-point", "query": "entailment",
            "symbols": [{"name": "hours", "sort": "Int", "meaning": "the hours the claim states"}],
            "premises": [{"id": "P_restated", "expr": concl, "label": "the claim restated", "grounding": g}],
            "conclusion": {"id": "C", "expr": concl, "label": "the claim"}}


@pytest.mark.parametrize("kind, refs, request_texts, docs, standing, why", [
    # a task setting that states only a number the request states for the quantity its symbol names (by its input, or by a
    # text supplied with it): no number match is evidence, so it is never a transcription, and the request does not refute
    # it: undecided (it was a transcription under the withdrawn rule figure-transcription)
    ("task_setting", None, ["Write about the hours: 12 hours a day."], (), "undecided", "a number match is no evidence"),
    ("task_setting", None, ["Write about the hours."], (ROTA_DOC,), "undecided", "a number match is no evidence"),
    ("task_setting", None, ["Write about the hours."], (), "refuted", "stated nowhere in the request"),
    # a supplied text with no excerpt: only the documents supplied with the request that it names can refute it
    ("supplied_text", ["doc-rota"], ["Write about the hours: 12 hours a day."], (ROTA_DOC,), "undecided", "a number match is no evidence"),
    ("supplied_text", ["doc-mill"], ["Write about the hours: 12 hours a day."], (ROTA_DOC,), "uncheckable",
     "which is not among the texts supplied with the request"),
    ("supplied_text", [], ["Write about the hours: 12 hours a day."], (ROTA_DOC,), "uncheckable", "names no document supplied with the request"),
    ("supplied_text", ["doc-rota"], ["Write about the hours."], (SuppliedText(document_id="doc-rota", title="Rota", author="Mill office", text="The shift ran long."),),
     "refuted", "stated nowhere in the document(s) doc-rota"),
    # never these kinds, however their figures stand
    ("rubric_rule", None, ["Write about the hours: 12 hours a day."], (ROTA_DOC,), "uncheckable", "no deterministic check verifies"),
    ("arithmetic_fact", None, ["Write about the hours: 12 hours a day."], (ROTA_DOC,), "own_kind", "not verified"),
])
def test_rule_same_quantity_a_label_with_no_excerpt_is_never_a_transcription_and_the_request_can_only_refute_it(kind, refs, request_texts, docs, standing, why):
    """Rule ``same-quantity`` (the third repair of the translator merge, decision 55), rewritten from
    ``test_rule_figure_transcription_verifies_a_label_with_no_excerpt_only_by_numbers_alone_that_the_request_states``,
    which pinned the fault the review found: rule ``figure-transcription`` took a ``task_setting`` or ``supplied_text``
    premise with no excerpt as a transcription when its numbers occurred in the request, so the claim's own count beside
    an 80-word limit, or a "show that" target, cleared a circular encoding. No grounding label and no number match is
    evidence on its own: every case is now the writer's own (the three it asserted transcriptions included), each with its
    standing (rule ``data-standing``) and the reason, and the six it asserted the writer's own keep their reasons."""
    rep = english_report(docs=(DOC, ROTA_DOC))
    rs = restatement(Problem.model_validate(_numeric_restating(kind, refs=refs)), rep, request_texts, request_documents=docs)
    assert rs.holds is True and (rs.own, rs.grounded) == (("P_restated",), ())
    assert rs.standings == (("P_restated", standing),)
    assert why in dict(rs.why_own)["P_restated"], rs.why_own
    # only a supplied text the receipt itself discloses as an unverified dependency; a task setting is presented as given
    assert rs.undecided_disclosed == (("P_restated",) if standing == "undecided" and kind == "supplied_text" else ())


@pytest.mark.parametrize("expr, sort, standing, why", [
    # a Boolean premise whose symbol the translation does not ground as data: a check shows it is not the request's
    (V("hours_ok"), "Bool", "refuted", "which the translation itself does not ground as data"),
    # no figure but 0 and 1 (structural, never read as data): nothing a check reads, so only the label presents it as data
    # (the fourth repair, decision 56: uncheckable; it asserted "undecided", the label-only class the review found)
    ({"op": "eq", "left": V("hours"), "right": {"op": "int", "value": "1"}}, "Int", "uncheckable", "no figure other than 0 or 1"),
    # a truth constant beside a figure the request states, in a premise whose statement names no quantity to read it for:
    # a number match only (decision 56: uncheckable; it asserted "undecided")
    ({"op": "and", "args": [{"op": "eq", "left": V("hours"), "right": {"op": "int", "value": "12"}}, {"op": "bool", "value": True}]}, "Int", "uncheckable",
     "a number match is no evidence"),
])
def test_rule_data_standing_a_premise_stating_more_than_numbers_is_never_verified_by_the_requests_numbers(expr, sort, standing, why):
    """Rewritten from ``test_rule_figure_transcription_never_verifies_a_premise_that_states_more_than_numbers_the_request_states``:
    a task setting whose premise is Boolean, holds a truth constant, or states no figure but 0 and 1 is never verified by
    the request's numbers, even when the request states the figures it has: the writer's own (the same assertions). Rule
    figure-transcription, whose reasons the test named, is withdrawn (decision 55: no premise with no excerpt is a
    transcription), so each case now names its standing (rule ``data-standing``) and the reason that gives it. The fourth
    repair (decision 56) makes the two cases it asserted "undecided" uncheckable (only the label presents them as data:
    a structural figure; a figure no statement of the premise names a quantity for), shown not to be data; every other
    assertion is kept and the shown standing is asserted for all three."""
    name = "hours_ok" if sort == "Bool" else "hours"
    prob = Problem.model_validate({"problem_id": "p-fig", "request_id": "req-ovs", "claim_id": "en-point", "query": "entailment",
                                   "symbols": [{"name": name, "sort": sort}],
                                   "premises": [{"id": "P_restated", "expr": expr, "grounding": {"kind": "task_setting"}}],
                                   "conclusion": {"id": "C", "expr": expr}})
    rs = restatement(prob, english_report(), ["Write about the hours: 12 hours a day, 1 shift."])
    assert rs.holds and rs.own == ("P_restated",) and why in dict(rs.why_own)["P_restated"], rs.why_own
    assert rs.standings == (("P_restated", standing),) and rs.grounded == ()
    # every case is shown not to be data now (decision 56), so a result resting on it is OVS-TRN-006, never OVS-TRN-011
    assert rs.shown == ("P_restated",) and rs.undecided == ()


def _form(premise: dict, conclusion: dict, symbols: dict[str, str], grounding: Optional[dict] = None) -> Problem:
    return Problem.model_validate({"problem_id": "p-form", "request_id": "req-ovs", "claim_id": "en-point", "query": "entailment",
                                   "symbols": [{"name": n, "sort": s} for n, s in symbols.items()],
                                   "premises": [{"id": "P", "expr": premise, "grounding": grounding or INFER}],
                                   "conclusion": {"id": "C", "expr": conclusion}})


def _n(v: str, op: str = "int") -> dict:
    return {"op": op, "value": v}


_E, _B, _Q, _X = V("endless"), V("bell"), V("q"), V("x")


#: The forms below that the translator's own E112 reads since the round-7 core fix (fidelity-4: the engine reads a premise as
#: written and in its normal form, ``engine/README.md``): double negation, ``e <-> true``, swapped ``eq`` operands, a flipped
#: comparison and a pair of bounds. ``e or e``, ``true implies e``, ``b and (b implies e)``, ``not (q != 105)``, identity
#: elements and the arithmetic forms are still read by the Overseer only.
ENGINE_READS = (
    {"op": "not", "arg": {"op": "not", "arg": _E}},
    {"op": "iff", "left": _E, "right": {"op": "bool", "value": True}},
    {"op": "eq", "left": _n("105"), "right": _Q},
    {"op": "lt", "left": _n("3"), "right": _Q},
    {"op": "and", "args": [{"op": "ge", "left": _Q, "right": _n("105")}, {"op": "le", "left": _Q, "right": _n("105")}]},
)


@pytest.mark.parametrize("premise, conclusion, symbols, way", [
    ({"op": "or", "args": [_E, _E]}, _E, {"endless": "Bool"}, "boolean"),
    ({"op": "implies", "left": {"op": "bool", "value": True}, "right": _E}, _E, {"endless": "Bool"}, "boolean"),
    ({"op": "not", "arg": {"op": "not", "arg": _E}}, _E, {"endless": "Bool"}, "syntactic"),  # as written once negation is pushed inward
    ({"op": "and", "args": [_B, {"op": "implies", "left": _B, "right": _E}]}, _E, {"endless": "Bool", "bell": "Bool"}, "boolean"),
    ({"op": "iff", "left": _E, "right": {"op": "bool", "value": True}}, _E, {"endless": "Bool"}, "boolean"),
    ({"op": "eq", "left": _n("105"), "right": _Q}, {"op": "eq", "left": _Q, "right": _n("105")}, {"q": "Int"}, "boolean"),
    ({"op": "lt", "left": _n("3"), "right": _Q}, {"op": "gt", "left": _Q, "right": _n("3")}, {"q": "Int"}, "boolean"),
    ({"op": "not", "arg": {"op": "ne", "left": _Q, "right": _n("105")}}, {"op": "eq", "left": _Q, "right": _n("105")}, {"q": "Int"}, "boolean"),
    ({"op": "eq", "left": {"op": "add", "args": [_X, _n("0")]}, "right": _n("5")}, {"op": "eq", "left": _X, "right": _n("5")}, {"x": "Int"}, "boolean"),
    ({"op": "eq", "left": {"op": "mul", "args": [_n("1.0", "real"), _X]}, "right": _n("5")}, {"op": "eq", "left": _X, "right": _n("5")}, {"x": "Real"}, "boolean"),
    ({"op": "and", "args": [{"op": "ge", "left": _Q, "right": _n("105")}, {"op": "le", "left": _Q, "right": _n("105")}]},
     {"op": "eq", "left": _Q, "right": _n("105")}, {"q": "Int"}, "order"),
    ({"op": "not", "arg": {"op": "lt", "left": _X, "right": _n("3")}}, {"op": "ge", "left": _X, "right": _n("3")}, {"x": "Int"}, "order"),
    # STEM repair 12 (decision 72, rule arithmetic-restatement): the conjunct rewritten by the arithmetic of its own symbols, its terms moved
    # across or both sides scaled. Before, every arithmetic term was opaque, so none restated anything ('2 * x eq 10' beside 'x eq 5' stood
    # among the controls below as an equation solved): a circular translation in that form carried its result with no finding
    ({"op": "eq", "left": {"op": "mul", "args": [_n("2"), _X]}, "right": _n("10")}, {"op": "eq", "left": _X, "right": _n("5")}, {"x": "Int"}, "arithmetic"),
    ({"op": "eq", "left": {"op": "sub", "left": V("c"), "right": _n("2.00", "real")}, "right": _n("0", "real")},
     {"op": "eq", "left": V("c"), "right": _n("2.00", "real")}, {"c": "Real"}, "arithmetic"),
    ({"op": "eq", "left": {"op": "mul", "args": [_n("2", "real"), V("c")]}, "right": _n("4.00", "real")},
     {"op": "eq", "left": V("c"), "right": _n("2.00", "real")}, {"c": "Real"}, "arithmetic"),
    ({"op": "eq", "left": {"op": "add", "args": [{"op": "mul", "args": [_n("2"), _X]}, _n("3")]}, "right": _n("7")}, {"op": "eq", "left": _X, "right": _n("2")},
     {"x": "Int"}, "arithmetic"),
    ({"op": "eq", "left": _n("0", "real"), "right": {"op": "sub", "left": V("c"), "right": _n("2.00", "real")}},
     {"op": "eq", "left": V("c"), "right": _n("2.00", "real")}, {"c": "Real"}, "arithmetic"),
    ({"op": "eq", "left": {"op": "div", "left": V("c"), "right": _n("2", "real")}, "right": _n("1.00", "real")},
     {"op": "eq", "left": V("c"), "right": _n("2.00", "real")}, {"c": "Real"}, "arithmetic"),
])
def test_rule_semantic_restatement_reads_a_restatement_in_another_form(premise, conclusion, symbols, way):
    """Rule ``semantic-restatement`` (the second repair, decision 51): a premise that restates the conclusion in another
    form than as written (``e or e``, ``true implies e``, ``not not e``, ``b and (b implies e)``, a reversed or negated
    comparison, an identity element beside a symbol, the order of numbers) restates it as the same expression does. The
    translator's rule reads the expression as written and in its normal form (``engine/README.md``; the round-7 core fix,
    fidelity-4), so it flags exactly the forms of ``ENGINE_READS`` and delivers the others; the Overseer's rule reads every
    one, and under a writer's-own grounding each is the conclusion assumed. (Rewritten to the stricter rule: the
    translator's reading of each form is pinned, where before the test pinned that it read none.)"""
    from epinoic_logic.engine.runner import circular_premises as translator_circular_premises
    prob = _form(premise, conclusion, symbols)
    assert translator_circular_premises(prob) == (["P"] if premise in ENGINE_READS else [])
    rs = restatement(prob, english_report(), [])
    assert rs.holds and rs.own == ("P",) and dict(rs.how)["P"] == (way,) and way in RESTATEMENT_WAYS


@pytest.mark.parametrize("premise, conclusion, symbols", [
    # a line of working, an equation solved, a substitution with a 1 among the numbers: the engine checks the computation
    ({"op": "eq", "left": V("a"), "right": {"op": "div", "left": {"op": "sub", "left": _n("20"), "right": _n("0")}, "right": _n("4.0", "real")}},
     {"op": "eq", "left": V("a"), "right": _n("5.0", "real")}, {"a": "Real"}),
    ({"op": "eq", "left": V("f"), "right": {"op": "mul", "args": [_n("1"), _n("10")]}}, {"op": "eq", "left": V("f"), "right": _n("10")}, {"f": "Int"}),
    # STEM repair 12: arithmetic of numbers alone stays the working the engine checks beside a symbol scaled ('2 * c eq 2 * 2.00') or alone
    # ('c eq 4.00 / 2'), and a premise not equivalent to the conjunct restates nothing (another value, a bound, a product of two symbols)
    ({"op": "eq", "left": V("c"), "right": {"op": "div", "left": _n("4.00", "real"), "right": _n("2", "real")}},
     {"op": "eq", "left": V("c"), "right": _n("2.00", "real")}, {"c": "Real"}),
    ({"op": "eq", "left": {"op": "mul", "args": [_n("2", "real"), V("c")]}, "right": {"op": "mul", "args": [_n("2", "real"), _n("2.00", "real")]}},
     {"op": "eq", "left": V("c"), "right": _n("2.00", "real")}, {"c": "Real"}),
    ({"op": "eq", "left": {"op": "mul", "args": [_n("2", "real"), V("c")]}, "right": _n("4.20", "real")},
     {"op": "eq", "left": V("c"), "right": _n("2.00", "real")}, {"c": "Real"}),
    ({"op": "ge", "left": {"op": "mul", "args": [_n("2"), _X]}, "right": _n("10")}, {"op": "eq", "left": _X, "right": _n("5")}, {"x": "Int"}),
    ({"op": "eq", "left": {"op": "mul", "args": [_X, V("y")]}, "right": _n("10")}, {"op": "eq", "left": _X, "right": _n("5")}, {"x": "Int", "y": "Int"}),
    # a value from which a weaker claim follows: a derivation, not the claim restated
    ({"op": "eq", "left": _X, "right": _n("5")}, {"op": "gt", "left": _X, "right": _n("3")}, {"x": "Int"}),
    # a definition by a comparison of numbers alone: the engine checks the comparison
    ({"op": "iff", "left": V("y12"), "right": {"op": "and", "args": [{"op": "ge", "left": _n("136"), "right": _n("133")}, {"op": "le", "left": _n("136"), "right": _n("144")}]}},
     V("y12"), {"y12": "Bool"}),
    # an implication whose antecedent no premise gives
    ({"op": "implies", "left": _B, "right": _E}, _E, {"endless": "Bool", "bell": "Bool"}),
])
def test_control_rule_semantic_restatement_reads_no_computation_or_derivation_as_a_restatement(premise, conclusion, symbols):
    """Controls: arithmetic of numbers alone is never a restatement (a line of working, ``1 * 10`` beside ``10``: a
    computation on numbers keeps its 1; ``4.00 / 2`` and ``2 * 2.00`` beside a symbol), nor a premise not equivalent to the
    conjunct (another value, a bound, a product of two symbols), a derivation of a weaker claim, a definition by a comparison
    of numbers, or an implication whose antecedent is not given. None of them is the conclusion assumed. (STEM repair 12: the
    conjunct rewritten by the arithmetic of its own symbols, '2 * x eq 10' beside 'x eq 5', is a restatement: above.)"""
    rs = restatement(_form(premise, conclusion, symbols), english_report(), [])
    assert not rs.holds and rs.own == () and rs.partial_own == () and rs.how == ()


def test_rule_semantic_restatement_a_tautology_conjoined_to_the_conclusion_needs_no_premise():
    """A conjunct true under every assignment (``bell or not bell``, ``x = x``) needs no premise, so conjoining one to the
    conclusion never keeps the rest from being restated as a whole (the translator's rule needs every conjunct restated,
    so it delivers this). Control: the same conclusion with a conjunct that is not a tautology and no premise is
    restated only in part."""
    taut = {"op": "or", "args": [_B, {"op": "not", "arg": _B}]}
    same = {"op": "eq", "left": _X, "right": _X}
    prob = _form(_E, {"op": "and", "args": [_E, taut, same]}, {"endless": "Bool", "bell": "Bool", "x": "Int"})
    rs = restatement(prob, english_report(), [])
    assert rs.holds and rs.own == ("P",)
    open_part = _form(_E, {"op": "and", "args": [_E, _B]}, {"endless": "Bool", "bell": "Bool"})
    rs2 = restatement(open_part, english_report(), [])
    # bell is left open (no premise, not a tautology): endless is restated only in part, by a specialist inference the
    # receipt lists among the result's ungrounded dependencies (rule receipt-disclosure)
    assert not rs2.holds and rs2.partial_own == () and rs2.disclosed_own == ("P",)


def _partially_assumed(grounding: dict, *, also_derived: bool = False) -> dict:
    """The point with a second conjunct (toil, "labour is a punishment") added to its conclusion and asserted by a premise
    grounded ``grounding``; the point itself stays derived from the two quotations (the specialist's link). With
    ``also_derived`` the specialist's reasoning gives toil too (from the bell line)."""
    p = genuine_problem()
    p["symbols"] = p["symbols"] + [{"name": "toil", "sort": "Bool", "meaning": "labour is a punishment", "grounding": grounding}]
    p["conclusion"] = {"id": "C", "expr": {"op": "and", "args": [V("endless"), V("toil")]}, "label": "work is endless and a punishment"}
    p["premises"] = p["premises"] + [{"id": "P_assumed", "expr": V("toil"), "label": "labour is a punishment", "grounding": grounding}]
    if also_derived:
        p["premises"].append({"id": "P_toil_link", "expr": {"op": "implies", "left": V("bell"), "right": V("toil")}, "label": "the bell line makes labour a punishment",
                              "grounding": INFER})
    return p


@pytest.mark.parametrize("grounding, disclosed", [
    ({"kind": "task_setting"}, False), ({"kind": "rubric_rule"}, False), ({"kind": "arithmetic_fact"}, False),
    ({"kind": "assumption"}, True), ({"kind": "specialist_inference"}, True), ({"kind": "general_knowledge"}, True),
    ({"kind": "supplied_text"}, True), ({"kind": "knowledge_document"}, True), ({"kind": "library_source"}, True),
])
def test_rule_receipt_disclosure_grades_a_premise_restating_part_of_the_conclusion_by_what_the_receipt_discloses(grounding, disclosed):
    """Rule ``receipt-disclosure`` (the second repair, decision 51): the conclusion's other conjunct is derived, so it is
    not restated as a whole; the writer's-own premise restating the rest is graded by the necessity run when the receipt
    presents it as given with the task (a task setting, rubric rule or arithmetic fact no check verified: neither the
    result's ungrounded nor its unverified dependencies list it), and is disclosed (no finding) otherwise."""
    from epinoic_logic.engine import verify
    from epinoic_logic.engine.results import SolverConfig as _SC
    obj = _partially_assumed(grounding)
    prob = Problem.model_validate(obj)
    rs = restatement(prob, english_report(), [])
    assert not rs.holds and rs.own == ()
    assert (rs.partial_own, rs.disclosed_own) == (((), ("P_assumed",)) if disclosed else (("P_assumed",), ()))
    res = verify(prob, _SC())
    listed = set(res.ungrounded_dependencies) | set(res.unverified_dependencies)
    # Rewritten by the second translator merge (decision 73), to the merged engine's stricter rule: it lists EVERY such
    # premise (a task-authority kind no check validated among the unverified dependencies, engine.authority), where the
    # earlier engine listed only the disclosed kinds; the overseer still grades the task-authority kinds (above), since
    # their label presents them as given with the task
    assert res.status.value == "ENTAILED" and "P_assumed" in listed
    if not disclosed:
        assert "P_assumed" in res.unverified_dependencies


def test_a_part_of_the_conclusion_assumed_under_a_task_setting_label_is_trn_006_and_the_disclosed_and_derived_controls_are_not():
    """The partial-label laundering the independent re-test found: a conjunct added to the claim and assumed under a
    ``task_setting`` label, beside a part the specialist's link derives, was no finding (the first repair graded only a
    conclusion restated as a whole). Now OVS-TRN-006, an error citing the auditor's run (COUNTEREXAMPLE without the
    premise). Controls: the same premise as an ``assumption`` (the receipt lists it as an ungrounded dependency) is a
    coverage note, and a task setting the specialist's reasoning also gives is no finding (the result does not rest on
    it)."""
    aud = make_auditor(shadow="off")
    try:
        aud, ch, rc = run({POINT: proposal(_partially_assumed({"kind": "task_setting"}))}, auditor=aud)
        o = next(x for x in rc.outcomes if x.claim_id == POINT)
        assert o.display_status.value == "ENTAILED" and not withheld_as_circular_by_the_translator(o)
        a = aud.audit(ch.uid)
        f = trn(a, "OVS-TRN-006")
        assert len(f) == 1 and f[0].severity == "error" and f[0].claim_ids == [POINT]
        assert all(w in f[0].message for w in ("part of its conclusion", "P_assumed", "receipt-disclosure", "COUNTEREXAMPLE")), f[0].message
        assert a.transfer_states[rc.message_id] == "AUDIT_FAILED"
    finally:
        aud.close()
    for grounding, also_derived, note in (({"kind": "assumption"}, False, "rule receipt-disclosure: no finding"),
                                          ({"kind": "task_setting"}, True, "does not rest on them")):
        aud2 = make_auditor(shadow="off")
        try:
            aud2, ch2, rc2 = run({POINT: proposal(_partially_assumed(grounding, also_derived=also_derived))}, auditor=aud2)
            a2 = aud2.audit(ch2.uid)
            assert trn(a2, "OVS-TRN-006") == [] and trn(a2, "OVS-TRN-010") == [], (grounding, also_derived)
            assert any(note in n and "P_assumed" in n for n in a2.coverage.notes), a2.coverage.notes
        finally:
            aud2.close()


def test_a_conjoined_transcription_never_hides_an_assumed_premise():
    """The other laundering the re-test found: the claim conjoined with a fact a verified quotation restates, the claim
    itself in place of the specialist's link under a ``task_setting`` label. The translator's rule reads both restating
    premises as transcriptions and delivers it; the overseer reads the conclusion as restated as a whole, P_coal a
    transcription and P_assumed the writer's own: OVS-TRN-006 naming P_assumed beside the transcription."""
    p = genuine_problem()
    p["conclusion"] = {"id": "C", "expr": {"op": "and", "args": [V("endless"), V("coal")]}, "label": "work is endless, counted in coal"}
    p["premises"] = [x for x in p["premises"] if x["id"] != "P_link"] + [{"id": "P_assumed", "expr": V("endless"), "grounding": {"kind": "task_setting"}}]
    rs = restatement(Problem.model_validate(p), english_report(), [EN_INPUT])
    assert rs.holds and rs.own == ("P_assumed",) and rs.grounded == ("P_coal",)
    aud = make_auditor(shadow="off")
    try:
        aud, ch, rc = run({POINT: proposal(p)}, auditor=aud)
        f = trn(aud.audit(ch.uid), "OVS-TRN-006")
        assert len(f) == 1 and "P_assumed" in f[0].message and "beside the transcription(s) P_coal" in f[0].message, f
    finally:
        aud.close()


# ============================================================================================ harness: genuine-only with STEM mutations
def _stem_round(tmp_path) -> "Path":
    """A one-task round of a Physics answer the merged arena's STEM mutations apply to (a worked chain whose stated result
    and substituted value can be changed)."""
    from pathlib import Path
    rnd = Path(tmp_path) / "rounds" / "rx"
    (rnd / "specialists").mkdir(parents=True)
    item = {"task_id": "ph-x", "subject": "Physics", "agent_id": "physics-specialist", "task_type": "structured_question", "supplied_texts": [],
            "question": "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration.",
            "response_text": "The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 5.0 m s⁻².\n\nThe acceleration is therefore 5.0 m s⁻²."}
    (rnd / "specialists" / "ph-x.json").write_text(json.dumps(item), encoding="utf-8")
    return rnd


def test_rule_genuine_only_switches_off_the_merged_arenas_stem_mutations(tmp_path):
    """The translator merge added STEM fault mutations to the arena beside its shared ones (``STEM_MUTATIONS``):
    ``genuine_only`` (the tampering suite's targets, the re-keyed r7 measurement) must switch both off, and restore both."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "overseer"))
    import ovs_harness as H
    ra = H.arena()
    before = (ra.MUTATIONS, ra.STEM_MUTATIONS)
    assert ra.STEM_MUTATIONS  # the merged arena mutates STEM answers
    aud = H.new_auditor(H.keyring_for("arena"))
    try:
        rr = H.replay_round(_stem_round(tmp_path / "a"), aud, genuine_only=True)
        assert [c.key for c in rr.channels] == ["ph-x"] and rr.results["transmissions"] == 1
    finally:
        aud.close()
    assert (ra.MUTATIONS, ra.STEM_MUTATIONS) == before  # restored
    # control: without genuine_only the STEM mutations run on the same answer
    aud2 = H.new_auditor(H.keyring_for("arena"))
    try:
        rr2 = H.replay_round(_stem_round(tmp_path / "b"), aud2)
        assert {c.key for c in rr2.channels} >= {"ph-x", "ph-x::stem_arithmetic_slip", "ph-x::stem_substitution"}
    finally:
        aud2.close()


# ============================================================================================ pack: the ledger codes as the merged channel raises them
def _ledger_codes_for_the_synthesis_rules() -> tuple[str, str]:
    """``(code, code)`` the merged ledger raises for a student-facing text that is not composed of its claims (rule
    text-composition) and for a paraphrase that negates its one source's own content (rule negated-source-content)."""
    from epinoic_logic.integrity.ledger import check_synthesis_ledger
    from epinoic_logic.integrity import SynthesizedClaim, Synthesis

    from .test_review1_content_checks import _hi_report
    src = "The Factory Act of 1833 banned the employment of children under nine in textile mills."
    rep = _hi_report(src)

    def syn(claim_text: str, text: str) -> Synthesis:
        claims = [SynthesizedClaim(claim_id="s1", text=claim_text, source_claim_ids=["h1.1"], transformation="paraphrased")]
        return Synthesis(synthesis_id="syn-1", request_id="req-ovs", task_id="task-ovs", combinator_agent_id="combinator", source_report_ids=["rep-hi-1"],
                         claims=claims, ledger=[], text=text, text_sha256=sha256_text(text), created_at="2026-10-11T12:00:00Z")
    composed = {f.code for f in check_synthesis_ledger([rep], syn(src, src + " It was never enforced."))}
    negated_text = "The Factory Act of 1833 did not ban the employment of children under nine in textile mills."
    negated = {f.code for f in check_synthesis_ledger([rep], syn(negated_text, negated_text))}
    (comp,) = [c for c in composed if c in ("INT-LEDGER-028", "INT-LEDGER-031")]
    (neg,) = [c for c in negated if c in ("INT-LEDGER-027", "INT-LEDGER-030")]
    return comp, neg


def _i68_i69(pack_version: str) -> tuple[str, str]:
    from epinoic_logic.overseer.pack import installed_pack_dir
    insp = (installed_pack_dir(pack_version) / "03-inspection.md").read_text(encoding="utf-8")
    i68 = insp.split("**I68 ", 1)[1].split("\n- **I69", 1)[0]
    i69 = insp.split("**I69 ", 1)[1].split("\n- **I70", 1)[0]
    return i68, i69


#: Sentences of the first staged pack 1.3 that read a grounding kind label as a transcription with nothing verified, so a
#: cheapest-tier agent would leave unaccused the circular encodings the merged translator delivers on a label alone (the
#: independent test's finding on the staged rebuild). None may come back.
LABEL_AS_TRANSCRIPTION = (
    "grounded in the task or a text (`task_setting`, `rubric_rule`, `supplied_text`, `knowledge_document`, `library_source`",
    "A restatement grounded in the task or a text",
    "The restating premise is grounded in the task or a text: no accusation",
    "a premise grounded in the task or a text that restates the conclusion: a transcription check",
    "restating premise grounded `task_setting`, `supplied_text` or `knowledge_document` | Leave it",
)


#: Sentences of pack 1.3 as the first repair corrected it (decision 49) that the second repair of the translator merge
#: corrected again (decision 51), so that the pack says exactly what the overseer's rules decide: a task setting read as a
#: transcription when "its numbers the request or the report states" (a condition a Boolean premise meets vacuously, so an
#: agent left a restatement under a ``task_setting`` label unaccused), and a premise restating the conclusion in another
#: form sent to the meaning check (rule semantic-restatement reads it as a restatement). None may come back.
TASK_SETTING_AS_TRANSCRIPTION = (
    "a task setting whose numbers the request or the report states",
    "or a `task_setting` whose numbers the request or the report states",
    "its `kind` is `task_setting`, its `verified` is not false, and every number in it is stated in `user_input` or the report",
    "or a `task_setting` the request states | Leave it",
    "A premise that only means the same in another form",
    "for a premise that means the same in another form | Use `translation_unfaithful`",
    "for a premise that only means the same as the conclusion | Use `translation_unfaithful`",
    "for a premise that wraps the conclusion in two `not` | Not the same expression",
)
#: What the second repair requires each document to say (file, words): the other forms of rule semantic-restatement, the
#: dependencies rule receipt-disclosure reads, K6's and the master prompt's task_setting label, and I85 as D26 defines a
#: clean member. (It also required I77's rule figure-transcription: "it states nothing but numbers" and "a `task_setting`
#: or `supplied_text` that neither way verifies"; the third repair withdrew that rule, so both sentences are refused now,
#: :data:`FIGURE_AS_TRANSCRIPTION`, and :data:`THIRD_REPAIR_RULES` requires what replaced them.)
SECOND_REPAIR_RULES = (
    ("03-inspection.md", "the premise says the conjunct in another form"),
    ("03-inspection.md", "its `ungrounded_dependencies` or `unverified_dependencies` list that premise"),
    ("03-inspection.md", "or ACCEPTED_WITH_FINDINGS whose only findings are INT-REQ-016 warnings naming other answers to the same input"),
    ("06-kinds-and-codes.md", "A restating premise grounded `task_setting`, `supplied_text`, `rubric_rule`, `knowledge_document` or `library_source` that no check verified"),
    ("master_prompt.txt", "A load-bearing restating premise grounded task_setting, supplied_text, rubric_rule, knowledge_document or library_source that no check verified"),
    ("master_prompt.txt", "A premise that says a conjunct of the conclusion in another form"),
    ("02-dossier.md", "The translator does not withhold a restatement grounded `task_setting`"),
)
#: Sentences of pack 1.3 as the second repair corrected it (decision 51) that the third repair (decision 55) withdrew with
#: rule figure-transcription: a task setting or supplied text with no excerpt read as a transcription when its numbers
#: occur in the request (a coincidental "80 words", or a "show that" target, then cleared the claim assumed). None may come
#: back.
FIGURE_AS_TRANSCRIPTION = (
    "it states nothing but numbers",
    "a `task_setting` or `supplied_text` that neither way verifies",
    "or a task setting or supplied text that states only numbers, every one of them stated in the request",
    "or it is a `task_setting` or `supplied_text` stating only numbers, every one stated in the request",
    "or it is a `task_setting` or `supplied_text` that states only numbers, every one stated in the request",
    "a `task_setting` or `supplied_text` stating only numbers the request states",
    "only numbers the request states verify it",
    "no number of the request can verify",
)
#: What the third repair requires each document to say (file, words): no number match is evidence (I77, the
#: ``translation_circular`` row and K6, the master prompt); the request can only refute a premise with no excerpt (a figure
#: stated only as the result to show, only for another quantity, only as a limit; the frequency words); the undecided
#: standing and OVS-TRN-011 (I77, the codes paragraph); where the translator records STEM units, in its own words (D30,
#: I92, the master prompt); and Example 28.
THIRD_REPAIR_RULES = (
    ("03-inspection.md", "A number of the request that matches is no evidence"),
    ("03-inspection.md", "only as the result the answer must show"),
    ("03-inspection.md", "only for another quantity than the premise's `label` and its symbols' `meaning` name"),
    ("03-inspection.md", "only as a limit"),
    ("03-inspection.md", "\"monthly\" 12"),
    ("03-inspection.md", "Every other `task_setting` or `supplied_text` premise with no excerpt is UNDECIDED"),
    ("03-inspection.md", "the checks report OVS-TRN-011, a warning, and decide nothing"),
    ("03-inspection.md", "The translator is told to record a unit as an assumption, never inside an expression"),
    ("02-dossier.md", "the translator is told to record a unit as an assumption, never inside an expression"),
    ("06-kinds-and-codes.md", "a number of the request that matches is no evidence"),
    ("06-kinds-and-codes.md", "OVS-TRN-011 (the result rests only on restating premises presented as data"),
    ("master_prompt.txt", "A number the request states is no evidence by itself"),
    ("master_prompt.txt", "records a unit as an assumption, never inside an expression"),
    ("07-examples.md", "## 31. Example 28: a \"show that\" target restated as given"),
)


#: Sentences of pack 1.3 as the third repair corrected it (decision 55) that the fourth repair (decision 56) withdrew: a
#: ``task_setting`` or ``supplied_text`` premise stating a Bool symbol the translation grounds as data throughout read as
#: UNDECIDED (so p proves p on labels alone was a warning to leave: Example 27 taught it). None may come back.
BOOL_AS_UNDECIDED = (
    "or it states a `Bool` symbol the translation grounds as data throughout",
    "Had the translation grounded the symbol and the conclusion as data, P1 would be undecided",
    "and the translation grounds wants_value and the conclusion as task data throughout. Both are undecided.",
    "## 30. Example 27: the question's data restated by task settings the request states",
    "| 27 | genuine, a transcription the code could not verify |",
)
#: What the fourth repair requires each document to say (file, words): a premise with no excerpt is undecided only when it
#: states values of quantities the request states for the quantities it names; a Bool symbol, anything else, 0 or 1, or a
#: bare number is what only its label presents as data (I77, the ``translation_circular`` row, K6, the master prompt); and
#: Examples 27 (faulty) and 29 (genuine).
FOURTH_REPAIR_RULES = (
    ("03-inspection.md", "it states a `Bool` symbol, whatever `symbols` and the conclusion's `grounding` say"),
    ("03-inspection.md", "it states anything but the values of quantities"),
    ("03-inspection.md", "a number in it is 0 or 1 (never read as data)"),
    ("03-inspection.md", "or the request states a number in it only bare"),
    ("03-inspection.md", "it states only values of quantities, and the request"),
    ("06-kinds-and-codes.md", "A premise that states a `Bool` symbol is never one of these: only its label presents it as data."),
    ("06-kinds-and-codes.md", "is shown not to be data whatever its symbols' and the conclusion's `grounding` say"),
    ("master_prompt.txt", "No check reads a Bool statement against the request"),
    ("07-examples.md", "## 30. Example 27: the question restated by a Bool task setting"),
    ("07-examples.md", "## 32. Example 29: the question's data restated by task settings the request states"),
)


#: What the fifth repair (decision 57, rule statement-context) requires each document to say: a number the request states
#: only in a yes/no question, under a negation, as one of alternatives, inside a claim to examine or as a requirement on
#: the answer (every ``constraints`` entry is one) is no statement of it (I77, K6, the wrong-verdict row, the master
#: prompt), an undecided premise's number is stated as a statement, and Example 30.
FIFTH_REPAIR_RULES = (
    ("03-inspection.md", "only where it does not state it as a statement: in a yes/no question"),
    ("03-inspection.md", "every entry of `constraints` is one"),
    ("03-inspection.md", "and it states it as a statement"),
    ("06-kinds-and-codes.md", "is never one of these: the checks show such a premise is not data"),
    ("06-kinds-and-codes.md", "or only in a yes/no question, under a negation, as one of alternatives, inside a claim the answer must examine or as a "
                              "requirement on the answer"),
    ("03-inspection.md", "as one of alternatives joined by \"or\""),
    ("master_prompt.txt", "and alternatives leave the number open"),
    ("master_prompt.txt", "a question asks, a negation denies, a requirement demands"),
    ("07-examples.md", "## 33. Example 30: a number the request only requires, restated as given"),
)


def _label_steering(pack_dir) -> list[str]:
    """Why the pack at ``pack_dir`` would steer an agent to read a grounding kind label as evidence (empty when it does not):
    a sentence of :data:`LABEL_AS_TRANSCRIPTION` or :data:`TASK_SETTING_AS_TRANSCRIPTION`, I77, K6 or the master prompt
    not saying that a label is no grounding, or a document not saying what :data:`SECOND_REPAIR_RULES` requires (the second
    repair of the translator merge made this stricter: a task_setting label and a restatement in another form); the third
    repair made it stricter again: a sentence of :data:`FIGURE_AS_TRANSCRIPTION` (a number match read as a transcription)
    is refused too, and every document must say what :data:`THIRD_REPAIR_RULES` requires; the fourth repair made it stricter
    again: a sentence of :data:`BOOL_AS_UNDECIDED` (a Bool premise read as undecided on its labels) is refused, and every
    document must say what :data:`FOURTH_REPAIR_RULES` requires; the fifth repair: and what :data:`FIFTH_REPAIR_RULES`
    requires."""
    from pathlib import Path
    d = Path(pack_dir)
    texts = {f: (d / f).read_text(encoding="utf-8") for f in ("02-dossier.md", "03-inspection.md", "06-kinds-and-codes.md", "07-examples.md", "master_prompt.txt")}
    out = [f"{f} still says {s!r}" for f, t in texts.items() for s in LABEL_AS_TRANSCRIPTION + TASK_SETTING_AS_TRANSCRIPTION + FIGURE_AS_TRANSCRIPTION
           + BOOL_AS_UNDECIDED if s in t]
    out += [f"{f} does not say {s!r}" for f, s in SECOND_REPAIR_RULES + THIRD_REPAIR_RULES + FOURTH_REPAIR_RULES + FIFTH_REPAIR_RULES if s not in texts[f]]
    i77 = texts["03-inspection.md"].split("**I77 ", 1)[1].split("\n- **I78", 1)[0]
    if "is a label the translator wrote, not evidence" not in i77:
        out.append("I77 does not say a grounding kind is a label, not evidence")
    own = i77.split("Every other restating premise is the writer's own", 1)
    if len(own) != 2 or not all(k in own[1].split("\n", 1)[0] for k in ("`rubric_rule`", "`knowledge_document`", "`library_source`", "`verified` is not true")):
        out.append("I77 does not count a rubric rule, a knowledge document, a library source or an unverified label among the writer's own")
    k6 = texts["06-kinds-and-codes.md"].split("**K6 ", 1)[1].split("\n- **K7", 1)[0]
    if "its label is not evidence" not in k6 or "`verified` is true" not in k6:
        out.append("K6 does not say a label is no grounding")
    if "A grounding kind is a label the translator wrote, not evidence" not in texts["master_prompt.txt"]:
        out.append("the master prompt does not say a grounding kind is a label")
    return out


def test_the_installed_pack_reads_no_grounding_kind_label_as_a_transcription(tmp_path):
    """Finding (d) of the independent test of the staged rebuild: pack 1.3 told agents (I77, K6, a mistakes row and the
    master prompt) that a restating premise grounded ``task_setting``, ``rubric_rule``, ``supplied_text``,
    ``knowledge_document`` or ``library_source`` is a transcription not to accuse, with no cited source, excerpt or
    verified check required. The corrected pack says a kind is a label, not evidence, as the overseer's rule
    ``grounded-transcription`` decides; a copy with one faulty sentence put back fails (the check is not vacuous)."""
    from epinoic_logic.overseer.pack import installed_pack_dir

    from .test_knowledge_pack import copy_pack
    assert _label_steering(installed_pack_dir("1.3")) == []
    d = copy_pack(tmp_path)
    prompt = (d / "master_prompt.txt").read_text(encoding="utf-8")
    old = ("- A translation the translator itself withheld as circular (INVALID_FORMALIZATION with E112) is not a circular translation to accuse, and neither "
           "is a restatement the code verified")
    assert old in prompt
    (d / "master_prompt.txt").write_text(prompt.replace(old, "- A restatement grounded in the task or a text, and a translation the translator itself "
                                                              "withheld as circular (INVALID_FORMALIZATION with E112), are not circular translations to accuse"),
                                         encoding="utf-8")
    assert _label_steering(d) != []


@pytest.mark.parametrize("sentence", TASK_SETTING_AS_TRANSCRIPTION)
def test_a_pack_that_takes_a_task_setting_label_or_another_form_as_a_transcription_again_is_refused(tmp_path, sentence):
    """The second repair of the translator merge (decision 51): pack 1.3 kept "a task setting whose numbers the request or
    the report states" as a transcription in the master prompt, I77, I81, K6 and a mistakes row, and sent a premise
    restating the conclusion in another form to the meaning check (I77, two mistakes rows, a wrong-verdict row). The
    installed pack says neither (the test above); each of those sentences put back into a copy is found."""
    from .test_knowledge_pack import copy_pack
    d = copy_pack(tmp_path)
    for name in ("03-inspection.md", "06-kinds-and-codes.md", "master_prompt.txt"):
        assert sentence not in (d / name).read_text(encoding="utf-8")
    target = d / ("master_prompt.txt" if sentence.startswith("a task setting") else "03-inspection.md")
    target.write_text(target.read_text(encoding="utf-8") + f"\n- {sentence}.\n", encoding="utf-8")
    assert any(sentence in why for why in _label_steering(d))


@pytest.mark.parametrize("sentence", FIGURE_AS_TRANSCRIPTION)
def test_a_pack_that_takes_a_number_match_as_a_transcription_again_is_refused(tmp_path, sentence):
    """The third repair of the translator merge (decision 55): pack 1.3 described rule figure-transcription (a task setting
    or supplied text with no excerpt verified by numbers alone that the request states) in I77, I81, K6, the
    ``translation_circular`` row, the master prompt, mistakes rows and Example 27. The installed pack says none of it (the
    test above); each sentence put back into a copy is found."""
    from .test_knowledge_pack import copy_pack
    d = copy_pack(tmp_path)
    for name in ("02-dossier.md", "03-inspection.md", "06-kinds-and-codes.md", "07-examples.md", "master_prompt.txt"):
        assert sentence not in (d / name).read_text(encoding="utf-8")
    target = d / "06-kinds-and-codes.md"
    target.write_text(target.read_text(encoding="utf-8") + f"\n- {sentence}.\n", encoding="utf-8")
    assert any(sentence in why for why in _label_steering(d))


@pytest.mark.parametrize("name, words", THIRD_REPAIR_RULES)
def test_a_pack_that_drops_a_rule_of_the_third_repair_is_refused(tmp_path, name, words):
    """Control: a copy of the pack without one of the words :data:`THIRD_REPAIR_RULES` requires is found."""
    from .test_knowledge_pack import copy_pack
    d = copy_pack(tmp_path)
    text = (d / name).read_text(encoding="utf-8")
    assert words in text
    (d / name).write_text(text.replace(words, "(removed)"), encoding="utf-8")
    assert f"{name} does not say {words!r}" in _label_steering(d)


@pytest.mark.parametrize("sentence", BOOL_AS_UNDECIDED)
def test_a_pack_that_reads_a_bool_premise_as_undecided_on_its_labels_again_is_refused(tmp_path, sentence):
    """The fourth repair of the translator merge (decision 56): pack 1.3 as the third repair corrected it called a
    ``task_setting`` or ``supplied_text`` premise stating a Bool symbol the translation grounds as data throughout
    undecided (I77), and Examples 26 and 27 taught it, so an agent left p proves p under a label unaccused. The installed
    pack says none of it; each sentence put back into a copy is found."""
    from .test_knowledge_pack import copy_pack
    d = copy_pack(tmp_path)
    for name in ("02-dossier.md", "03-inspection.md", "06-kinds-and-codes.md", "07-examples.md", "master_prompt.txt"):
        assert sentence not in (d / name).read_text(encoding="utf-8")
    target = d / "03-inspection.md"
    target.write_text(target.read_text(encoding="utf-8") + f"\n- {sentence}.\n", encoding="utf-8")
    assert any(sentence in why for why in _label_steering(d))


@pytest.mark.parametrize("name, words", FOURTH_REPAIR_RULES)
def test_a_pack_that_drops_a_rule_of_the_fourth_repair_is_refused(tmp_path, name, words):
    """Control: a copy of the pack without one of the words :data:`FOURTH_REPAIR_RULES` requires is found."""
    from .test_knowledge_pack import copy_pack
    d = copy_pack(tmp_path)
    text = (d / name).read_text(encoding="utf-8")
    assert words in text
    (d / name).write_text(text.replace(words, "(removed)"), encoding="utf-8")
    assert f"{name} does not say {words!r}" in _label_steering(d)


def test_the_pack_says_where_the_translator_records_stem_units_in_its_own_words():
    """Finding (d) of the review: D30 and I92 said a unit is in the symbol's meaning or the premise's label, while the
    translator's guidance says to record a unit as an assumption, never inside an expression. The pack now quotes the
    guidance's own words (and the places such a record may be found); the guidance is pinned here so the two cannot drift."""
    from epinoic_logic.overseer.pack import installed_pack_dir
    from epinoic_logic.translate.subjects import STEM_ENCODING_GUIDANCE
    assert "record a unit as an assumption, never inside an expression" in STEM_ENCODING_GUIDANCE
    d = installed_pack_dir("1.3")
    for name in ("02-dossier.md", "03-inspection.md", "master_prompt.txt"):
        text = (d / name).read_text(encoding="utf-8")
        assert "record a unit as an assumption" in text or "records a unit as an assumption" in text, name
        assert "in the symbol's `meaning` or the premise's `label`, never in an expression" not in text, name
        assert "A unit belongs in the symbol's `meaning` or the premise's `label`" not in text, name
        # the fourth repair (decision 56): every place that says where a unit is recorded says it in the guidance's words
        # (the overview, an I97 bullet and a dossier mistakes row had "outside every expression")
        assert "outside every expression" not in text and "units recorded outside the expressions" not in text, name


@pytest.mark.parametrize("name, words", SECOND_REPAIR_RULES)
def test_a_pack_that_drops_a_rule_of_the_second_repair_is_refused(tmp_path, name, words):
    """Control: a copy of the pack without one of the words :data:`SECOND_REPAIR_RULES` requires is found (the check is
    not vacuous)."""
    from .test_knowledge_pack import copy_pack
    d = copy_pack(tmp_path)
    text = (d / name).read_text(encoding="utf-8")
    assert words in text
    (d / name).write_text(text.replace(words, "(removed)"), encoding="utf-8")
    assert f"{name} does not say {words!r}" in _label_steering(d)


def test_the_installed_pack_names_the_ledger_codes_the_merged_channel_raises():
    """Inspection I68 and I69 tell an agent which receipt finding settles a synthesis-text fault and a negated
    paraphrase; the translator merge renumbered both (the development branch gave INT-LEDGER-027 and -028 to a dropped
    from-memory label and a misspelt quotation), so the installed pack must name the codes the merged ledger raises,
    or an agent would accuse a receipt for lacking a code it is never meant to carry."""
    import re
    comp, neg = _ledger_codes_for_the_synthesis_rules()
    assert (comp, neg) == ("INT-LEDGER-031", "INT-LEDGER-030")
    i68, i69 = _i68_i69("1.3")
    assert comp in i68 and neg in i69
    assert not set(re.findall(r"INT-LEDGER-\d{3}", i68 + i69)) & {"INT-LEDGER-027", "INT-LEDGER-028"}
    # control: the pinned pre-merge pack 1.2 names the numbers the merge gave to other rules
    old68, old69 = _i68_i69("1.2")
    assert comp not in old68 and "INT-LEDGER-028" in old68 and neg not in old69 and "INT-LEDGER-027" in old69


@pytest.mark.parametrize("name, words", FIFTH_REPAIR_RULES)
def test_a_pack_that_drops_a_rule_of_the_fifth_repair_is_refused(tmp_path, name, words):
    """Control: a copy of the pack without one of the words :data:`FIFTH_REPAIR_RULES` requires is found."""
    from .test_knowledge_pack import copy_pack
    d = copy_pack(tmp_path)
    text = (d / name).read_text(encoding="utf-8")
    assert words in text
    (d / name).write_text(text.replace(words, "(removed)"), encoding="utf-8")
    assert f"{name} does not say {words!r}" in _label_steering(d)

