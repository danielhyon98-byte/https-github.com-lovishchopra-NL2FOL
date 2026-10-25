"""Regression tests for the content-check defects found by adversarial review round 3 of the Overseer (each fails on the
code before the fix; the scenarios are the reviewers' own, run through the contained harness's synthetic task):

* the blocker: the student-facing synthesis text negated, renamed, inverted or extended while every synthesized claim
  stayed faithful was released; the text must now be a composition of its claims (INT-LEDGER-031, error; INT-LEDGER-028 before
  the translator merge, which gave that number to a misspelt quotation);
* a synthesis exchanging the Acts' NAMES (not their years) re-pairs years with events (rule ``name-partner``);
* a forwarded answer altered and padded with background prose evades PEER-002 no longer (``contains-answer``), while a
  source document the answer quotes is never linked to the answer (``source-predates-answer``);
* the R11 re-parse compares whole claims, so an inflated certainty is CUST-006;
* a claim made only of markup or invisible characters (a thematic break) is never FID-001;
* a sentence QUOTING a supplied text's claim of accuracy is not FID-005.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ovs_harness as H  # noqa: E402
import tamper as T  # noqa: E402

from epinoic_logic.branches import RouterHub  # noqa: E402
from epinoic_logic.channel import TranslatorChannel  # noqa: E402
from epinoic_logic.integrity import AgentRole, LedgerEntry, SynthesizedClaim, WorkPlan  # noqa: E402
from epinoic_logic.integrity.ledger import check_synthesis_ledger, figure_pairing_differences, text_outside_claims  # noqa: E402
from epinoic_logic.overseer.checks.fidelity import claim_occurs  # noqa: E402
from epinoic_logic.overseer.checks import normalise, plain_form  # noqa: E402
from epinoic_logic.overseer.policy import release_decision  # noqa: E402
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text  # noqa: E402

from .conftest import CFG, KEY, make_auditor  # noqa: E402


def _auditor(**kw):
    return H.new_auditor(H.keyring_for("synthetic"), **kw)


def _errors(audit) -> set[str]:
    return {f.code for f in audit.report.findings if f.severity == "error"}


def _release(run, audit):
    a = run.auditor
    return release_decision(run.receipts["syn"], audit, a.keyring, audits=a.audits(run.uid), journal=a.journal(run.uid), message=run.messages.get("syn"))


# ============================================================================================ the blocker: synthesis text
GOOD = T.default_synthesis()
BASE = GOOD.text


def _with_text(text):
    return GOOD.model_copy(update={"text": text, "text_sha256": sha256_text(text)})


@pytest.mark.parametrize("label,text", [
    ("negated", BASE.replace("banned the employment", "did not ban the employment")),
    ("antonym", BASE.replace("banned", "allowed")),
    ("Act name exchanged", BASE.replace("The Factory Act of 1833", "The Ten Hours Act of 1833")),
    ("qualifier dropped", BASE.replace(" under nine", "")),
    ("sentence added with no figure", BASE + " Historians agree the Act was a complete failure and was soon repealed."),
    ("judgement inverted", BASE.replace("mattered most", "mattered least")),
])
def test_a_synthesis_text_saying_what_its_claims_do_not_is_never_released(label, text):
    a = _auditor(shadow="off")
    try:
        r = T.run_synthetic(a, synthesis=_with_text(text))
        rc = r.receipts["syn"]
        assert ("INT-LEDGER-031", "error") in {(f.code, f.severity) for f in rc.findings}, label
        audit = r.audit(final=True)
        d = _release(r, audit)
        assert not d.allowed and "INT-LEDGER-031" in d.reason, label
    finally:
        a.close()


def test_the_genuine_synthesis_text_and_connectives_between_claims_stay_clean():
    claims = [c.text for c in GOOD.claims]
    assert text_outside_claims(BASE, claims) == []
    joined = f"{claims[0]}. Moreover, {claims[1]} However, {claims[2]}"
    assert text_outside_claims(joined, claims) == []
    assert text_outside_claims("## Summary\n\n1. " + claims[0] + "\n2. " + claims[1] + "\n3. " + claims[2], claims) == []
    # a causal connective asserts a relation no claim states
    assert text_outside_claims(f"{claims[0]}, because {claims[1]}", claims)
    a = _auditor(shadow="off")
    try:
        r = T.run_synthetic(a, synthesis=GOOD)
        assert not [f for f in r.receipts["syn"].findings if f.code in ("INT-LEDGER-031", "INT-LEDGER-028")]
        assert _release(r, r.audit(final=True)).allowed
    finally:
        a.close()


# ============================================================================================ name-partner
S1 = SynthesizedClaim(claim_id="s1", text="The writer presents work as endless", source_claim_ids=["en-point"], transformation="carried")
S3 = SynthesizedClaim(claim_id="s3", text="On balance, the Act mattered most because it established inspection.", source_claim_ids=["h1.3"], transformation="carried")
DROP_EN = LedgerEntry(source_claim_ids=["en-ev1", "en-ev2", "en-an"], transformation="dropped", reason="supporting evidence summarised by the carried point")


def _syn(text, src, tr="carried"):
    led = [DROP_EN]
    if "h1.2" not in src:
        led = led + [LedgerEntry(source_claim_ids=["h1.2"], transformation="dropped", reason="supporting detail beyond the synthesis's scope")]
    return T.default_synthesis(claims=[S1, SynthesizedClaim(claim_id="s2", text=text, source_claim_ids=src, transformation=tr), S3], ledger=led)


@pytest.mark.parametrize("label,text,src,tr,repaired", [
    ("control carried", "The Factory Act of 1833 banned the employment of children under nine in textile mills.", ["h1.1"], "carried", False),
    ("control merged", "The Factory Act of 1833 banned the employment of children under nine in textile mills, and the Ten Hours Act of 1847 followed it.",
     ["h1.1", "h1.2"], "merged", False),
    ("V1 carried, entity swapped", "The Ten Hours Act of 1833 banned the employment of children under nine in textile mills.", ["h1.1"], "carried", True),
    ("V1b paraphrased, entity swapped", "In 1833 the Ten Hours Act banned employing children under nine in textile mills.", ["h1.1"], "paraphrased", True),
    ("V3 merged, names swapped", "The Ten Hours Act of 1833 banned the employment of children under nine in textile mills, and the Factory Act of 1847 followed it.",
     ["h1.1", "h1.2"], "merged", True),
    ("V10 merged, age moved to the other Act", "The Factory Act of 1833 banned the employment of children in textile mills, and the Ten Hours Act of 1847, "
     "which followed it, set the age at nine.", ["h1.1", "h1.2"], "merged", True),
])
def test_a_synthesis_exchanging_the_acts_names_re_pairs_their_years(label, text, src, tr, repaired):
    a = _auditor(shadow="off")
    try:
        r = T.run_synthetic(a, synthesis=_syn(text, src, tr))
        f = [x for x in r.receipts["syn"].findings if x.code == "INT-LEDGER-023" and "s2" in x.claim_ids]
        assert bool(f) is repaired, label
        if repaired:
            assert "re-paired" in f[0].message
            assert not _release(r, r.audit(final=True)).allowed
    finally:
        a.close()


def test_a_name_no_report_pairs_with_another_figure_is_not_a_re_pairing():
    src = ["The Factory Act of 1833 banned the employment of children under nine in textile mills.",
           "The Ten Hours Act of 1847 followed the Factory Act of 1833."]
    assert figure_pairing_differences("Althorp's Act of 1833 banned the employment of children under nine in textile mills.", src) == []
    assert figure_pairing_differences("The Act of 1833 banned the employment of children under nine in textile mills.", src) == []
    assert figure_pairing_differences("In 1833 the Factory Act, which the Ten Hours Act of 1847 followed, banned the employment of children under nine.", src) == []


# ============================================================================================ peer padding and source precision
PAD = ("Background for the reviewer. The early Victorian reform period saw parliament respond to campaigns by factory reformers, "
       "evangelical groups and medical witnesses, and historians still debate how far these measures were enforced in practice. "
       "Inspectors were few, mill owners were often magistrates themselves, and parents sometimes lied about ages so that wages kept coming in. ")
ALTERED = T.HI_TEXT.replace("1833", "1834").replace("under nine", "under twelve")


@pytest.mark.parametrize("label,text,author,identical,peer002", [
    ("altered answer padded", PAD + ALTERED, "router", False, True),
    ("altered answer quoted inside a sentence and padded", PAD + "The history specialist wrote: " + ALTERED, "router", False, True),
    ("the answer verbatim among background, attributed to the router", PAD + T.HI_TEXT, "router", True, True),
    ("the answer verbatim among background, attributed to its agent", PAD + T.HI_TEXT, "history-specialist", True, False),
])
def test_a_forwarded_answer_padded_with_background_is_held_to_byte_identity(label, text, author, identical, peer002):
    a = _auditor(shadow="off")
    out = {}

    def before(r):
        reply = r.messages["rep_hi"]
        _f, rf = r.channel.relay("router", AgentRole.ROUTER, "english-specialist", AgentRole.SPECIALIST, SpecialistReport.model_validate(reply.payload),
                                 in_reply_to=reply.message_id)
        doc = SuppliedText(document_id="background", title="Context", author=author, text=text)
        _m, _q, rq = r.hub.dispatch(r.key, "english-specialist", "Analyse how the writer presents work in the extract, using the context. Write no more than 80 words.",
                                    [T.DOC, doc])
        out["rq"] = rq
    try:
        r = T.run_synthetic(a, plan=T.make_plan(allowed_document_ids=[]), peer=False, synthesis=False, before_synthesis=before)
        rq = out["rq"]
        t = r.view().by_message[rq.message_id]
        assert [(p.document_id, p.report_id, p.identical) for p in t.peer_links] == [("background", "rep-hi-1", identical)], label
        clr = r.hub.clearance(r.key, rq.message_id, receipt=rq)
        assert ("OVS-PEER-002" in clr.codes) is peer002, label
    finally:
        a.close()


SRC = SuppliedText(document_id="source-a", title="Source A", author="A British diplomat, report of 1923",
                   text="The occupation of the Ruhr has brought German industry to a standstill and the mark has lost almost all of its value. "
                        "Ordinary families now carry their wages home in baskets.")
ANSWER1 = ('According to Source A, "The occupation of the Ruhr has brought German industry to a standstill and the mark has lost almost all of its value." '
           'It adds that "Ordinary families now carry their wages home in baskets."')


def _paper1_hub(extra_documents=()):
    hub = RouterHub(signing_key=KEY, key_id="hub", config=CFG, auditor=make_auditor())
    hub.open_task(WorkPlan(plan_id="plan-p1", request_id="req-p1", task_id="p1", subject="History", task_type="short_answer",
                           selected_agent_ids=["history-specialist", "history-specialist-2", "combinator"],
                           allowed_document_ids=["source-a", "peer:q1a", *extra_documents]))
    return hub


@pytest.mark.parametrize("variant", ["same agent, second question", "second agent, same source", "answer forwarded, then both texts"])
def test_a_source_document_the_answer_quotes_is_never_linked_to_the_answer(variant):
    hub = _paper1_hub()
    try:
        m1, _r, _q = hub.dispatch("p1", "history-specialist", "Q1a. What, according to Source A, were the effects of the occupation of the Ruhr?", [SRC])
        r1, rc1 = hub.receive("p1", m1.message_id, ANSWER1, agent_id="history-specialist", report_id="rep-q1a")
        agent, docs = "history-specialist", [SRC]
        if variant == "second agent, same source":
            agent = "history-specialist-2"
        if variant == "answer forwarded, then both texts":
            agent = "history-specialist-2"
            ch = hub.channels["p1"]
            ch.relay("router", AgentRole.ROUTER, agent, AgentRole.SPECIALIST, SpecialistReport.model_validate(r1.payload), in_reply_to=r1.message_id)
            docs = [SRC, SuppliedText(document_id="peer:q1a", title="Answer to Q1a", author="history-specialist", text=r1.payload["original_response"])]
        m2, _r2, rq2 = hub.dispatch("p1", agent, "Q1b. What is the message of Source A about German society?", docs)
        assert rq2.status.value == "ACCEPTED"
        _r2b, _rc2 = hub.receive("p1", m2.message_id, "Source A suggests that hyperinflation impoverished ordinary German families.", agent_id=agent,
                                 report_id="rep-q1b")
        audit = hub.audit("p1")
        assert "OVS-PEER-002" not in _errors(audit), variant
        for rc in hub.channels["p1"].receipts:
            assert hub.clearance("p1", rc.message_id, receipt=rc).state != "AUDIT_FAILED", variant
    finally:
        hub.close()


MORE_A = " The occupation also deepened resentment of France, and the government in Berlin called for passive resistance."


@pytest.mark.parametrize("variant,doc,peer002", [
    ("the same source under another document id", SuppliedText(document_id="source-a-extract", title="Source A (extract)", text=SRC.text), False),
    ("a longer document containing the source", SuppliedText(document_id="source-a-full", title="Source A (full report)", text=SRC.text + MORE_A), False),
    ("control: the answer itself, one quoted word altered, under a neutral id", SuppliedText(document_id="notes", title="Notes", author="router",
                                                                                         text=ANSWER1.replace("standstill", "halt")), True),
])
def test_a_text_resembling_the_answer_only_where_it_copied_its_source_is_never_linked(variant, doc, peer002):
    """Rule ``source-explained`` (beyond the reviewer's same-id case): a later text that resembles the answer only where the
    answer copied an earlier source (the same passage under another document id, a longer document containing it) is not
    taken to present the answer; the answer itself, altered and supplied under a neutral id, still is (PEER-002)."""
    hub = _paper1_hub(extra_documents=[doc.document_id])
    try:
        m1, _r, _q = hub.dispatch("p1", "history-specialist", "Q1a. What, according to Source A, were the effects of the occupation of the Ruhr?", [SRC])
        hub.receive("p1", m1.message_id, ANSWER1, agent_id="history-specialist", report_id="rep-q1a")
        m2, _r2, rq2 = hub.dispatch("p1", "history-specialist-2", "Q1b. What is the message of the source about German society?", [doc])
        assert rq2.status.value == "ACCEPTED"
        hub.receive("p1", m2.message_id, "Source A suggests that hyperinflation impoverished ordinary German families.", agent_id="history-specialist-2",
                    report_id="rep-q1b")
        audit = hub.audit("p1")
        assert ("OVS-PEER-002" in _errors(audit)) is peer002, variant
        assert (hub.clearance("p1", rq2.message_id, receipt=rq2).state == "AUDIT_FAILED") is peer002, variant
    finally:
        hub.close()


# ============================================================================================ re-parse compares whole claims
HEDGED = ("The Factory Act of 1833 may have banned the employment of children under nine in textile mills. "
          "The Ten Hours Act of 1847 followed the Factory Act of 1833. "
          "On balance, the Act mattered most because it established inspection.")
_ORIG_BRANCH_FOR = TranslatorChannel._branch_for


class _InflatingParser:
    def __init__(self, inner):
        self.inner = inner

    def parse_response(self, *a, **kw):
        rep = self.inner.parse_response(*a, **kw)
        return rep.model_copy(update={"claims": [c.model_copy(update={"certainty": "established"}) for c in rep.claims]})

    def __getattr__(self, name):
        return getattr(self.inner, name)


class _InflatingBranch:
    def __init__(self, inner):
        self.inner = inner

    def parser(self):
        return _InflatingParser(self.inner.parser())

    def __getattr__(self, name):
        return getattr(self.inner, name)


def _inflating_branch_for(self, agent_id):
    b, p = _ORIG_BRANCH_FOR(self, agent_id)
    return (_InflatingBranch(b), p) if agent_id == "history-specialist" else (b, p)


def test_a_parse_stage_that_inflates_certainty_is_cust_006_live():
    a = _auditor(shadow="off")
    try:
        with H.patched((TranslatorChannel, "_branch_for", _inflating_branch_for)):
            r = T.run_synthetic(a, hi_text=HEDGED, synthesis=False)
        rc = r.receipts["rep_hi"]
        rep = r.view().by_message[rc.message_id].report
        assert next(c.certainty for c in rep.claims if c.claim_id == "h1.1") == "established"
        clr = r.hub.clearance(r.key, rc.message_id, receipt=rc, wait_ms=0)
        a.drain()
        clr = r.hub.clearance(r.key, rc.message_id, receipt=rc)
        assert clr.state == "AUDIT_FAILED" and "OVS-CUST-006" in clr.codes
        f = [x for x in r.audit().report.findings if x.code == "OVS-CUST-006"]
        assert f and "certainty" in f[0].message
    finally:
        a.close()


def test_the_genuine_hedged_parse_is_not_cust_006():
    a = _auditor(shadow="off")
    try:
        r = T.run_synthetic(a, hi_text=HEDGED, synthesis=False)
        assert "OVS-CUST-006" not in {f.code for f in r.audit().report.findings}
    finally:
        a.close()


# ============================================================================================ empty comparison forms
@pytest.mark.parametrize("claim", ["*", "* *", "_", "**", "__", "_ _ _", "​", "⁠", "-"])
def test_a_claim_of_markup_or_invisible_characters_is_never_absent(claim):
    response = f"The first paragraph states a fact.\n\n{claim}\n\nThe second paragraph states another."
    assert claim_occurs(claim, normalise(response), plain_response=plain_form(response), raw_response=response)
    assert claim_occurs(claim, normalise(response), plain_response=plain_form(response))  # an empty form never decides absence


def test_a_thematic_break_delivered_as_a_claim_is_not_fid_001():
    text = ("The Factory Act of 1833 banned the employment of children under nine in textile mills.\n\n***\n\n"
            "The Ten Hours Act of 1847 followed the Factory Act of 1833.")
    a = _auditor(shadow="off")
    try:
        r = T.run_synthetic(a, hi_text=text, synthesis=False, peer=False)
        audit = r.audit()
        assert "OVS-FID-001" not in _errors(audit)
    finally:
        a.close()


def test_a_claim_absent_from_the_response_is_still_fid_001():
    response = "The writer presents work as endless."
    assert not claim_occurs("The writer presents work as joyful", normalise(response), plain_response=plain_form(response), raw_response=response)


# ============================================================================================ quoted self-certification
def test_a_quoted_claim_of_accuracy_is_analysis_not_a_self_certification():
    from epinoic_logic.adapters.markdown import is_self_certification, mask_quotations
    sentence = 'The brochure builds trust through an appeal to authority: "Every figure in this brochure has been independently verified."'
    assert is_self_certification(sentence) and not is_self_certification(mask_quotations(sentence))
    doc = SuppliedText(document_id="doc-mill", title="Brochure", author="Mill owners",
                       text="Every figure in this brochure has been independently verified. Nine out of ten customers return within a year.")
    claims = [dict(claim_id="p1-point", claim_text=sentence, claim_role="point", materiality="material"),
              dict(claim_id="p1-q01", claim_text='"Every figure in this brochure has been independently verified."', claim_role="evidence", materiality="supporting",
                   source_refs=[T.SourceRef(document_id="doc-mill", excerpt="Every figure in this brochure has been independently verified.")])]
    rep = T.english_report(sentence, claims, docs=(doc,))
    a = _auditor(shadow="off")
    try:
        r = T.run_synthetic(a, en_report=rep, synthesis=False, peer=False, problems={})
        audit = r.audit()
        assert not [f for f in audit.report.findings if f.code == "OVS-FID-005"]
    finally:
        a.close()


def test_the_specialists_own_self_certification_is_still_fid_005():
    text = T.EN_TEXT + " I have checked every quotation and all of them are verified."
    claims = [dict(c) for c in T.EN_CLAIMS] + [dict(claim_id="en-self", claim_text="I have checked every quotation and all of them are verified.",
                                                    claim_role="analysis", materiality="material")]
    a = _auditor(shadow="off")
    try:
        r = T.run_synthetic(a, en_report=T.english_report(text, claims), synthesis=False, peer=False)
        assert any(f.code == "OVS-FID-005" and "en-self" in f.claim_ids for f in r.audit().report.findings)
    finally:
        a.close()


def test_check_synthesis_ledger_reads_the_reports_context_for_names():
    """The name-partner rule reads the cited reports' other claims: the carried claim cites only h1.1, and the report's
    h1.2 says the Ten Hours Act is 1847's."""
    a = _auditor(shadow="off")
    try:
        r = T.run_synthetic(a, synthesis=False)
        reports = [r.view().by_message[r.receipts[k].message_id].report for k in ("rep_en", "rep_hi")]
        syn = _syn("The Ten Hours Act of 1833 banned the employment of children under nine in textile mills.", ["h1.1"])
        assert any(f.code == "INT-LEDGER-023" and "re-paired name" in f.message for f in check_synthesis_ledger(reports, syn))
    finally:
        a.close()
