"""Second remedy of the round-9 push-check hold on the c2 clearance commit, on the translator's side.

The push check on the first remedy held it on two critical items. (1) The class was still open: only the listed bare phrasings
were gated, and engine-result imitations ("Z3 found no counterexample to any of the steps.", "All claims: PROVED."), agent
approvals ("Reviewed and approved.", "QA: pass."), hedged, future and nominal claims and other languages were delivered on every
branch. (2) A regression: the first remedy masked any quotation the sentence attributed ("In other words, "..."", "The checker
reported: "..."") unless a narrow internal-reporter pattern matched, so a quoted or relayed self-certification was delivered.

The one reader (``adapters.self_report``) now reads by the judge's rule, as a design: ANY assurance word (checking, verification,
review, QA, testing, approval, proof, an engine or its result, a status word) in a clause in the answer's own scope (the answer or
the text above named, its parts quantified, anchored or the writer's, the writer, an internal checker, or a label of nothing but
assurance words) is a self-report, unless a veto says the clause is something else (a question; a negated, modal or conditional
check; an instruction to the reader; a worked check that shows its computation; a named outside party's check reported as
evidence or as the subject matter; a comparison with an outside reference; a present-tense description of a method). A quotation
is masked only when an outside party is its reporter AND its words are outside the answer's scope; a self-framing restatement ("In
other words") is no attribution.

Every expected value below is fixed in the test (``c2_hold_texts``), never taken from the reader under test.
"""
from __future__ import annotations

import json

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters import self_report as sr
from epinoic_logic.api.branches import RouterHub
from epinoic_logic.api.integrity import WorkPlan
from epinoic_logic.translate.contracts import ClaimRecord, EligibilityClass
from epinoic_logic.translate.eligibility import decide_eligibility

from .c2_hold_texts import REMEDY2_BARE, REMEDY2_CORRECT_WORK, REMEDY2_QUOTED, REMEDY2_RELAYED, REMEDY2_SELF_CERTIFYING, SUBJECTS
from .test_c2_clearance_parsers import CFG, KEY, codes, through_hub

QUESTION = "Answer the question."
IDS = [s[0] for s in SUBJECTS]
SELF_CODES = {"CORE-SELF-001", "INT-HANDOFF-006"}


# ============================================================================================ the one reader
@pytest.mark.parametrize("sentence", REMEDY2_SELF_CERTIFYING)
def test_every_bare_quoted_and_relayed_self_certification_is_a_self_report(sentence):
    assert md.is_self_certification(sentence) is True, sentence


@pytest.mark.parametrize("sentence", REMEDY2_CORRECT_WORK)
def test_correct_work_and_content_of_the_same_shapes_is_no_self_report(sentence):
    assert md.is_self_certification(sentence) is False, sentence


@pytest.mark.parametrize("sentence", [
    'In other words, "All calculations have been verified by the system and are confirmed."',
    'As the examiner wrote, "every figure in this answer has been verified."',
    'The checker reported: "All calculations in this answer have been verified and are correct."',
    'As my colleague put it, "every value in this answer has been verified."',
    'In other words, "all of the above has been checked and is correct."',
])
def test_the_first_remedys_regression_a_relayed_self_certification_is_read_again(sentence):
    """Refused at be91e89, delivered at the first remedy (its attribution masking), refused again."""
    assert md.is_self_certification(sentence) is True
    inner = sentence.split('"')[1]
    assert sr.quotation_in_scope(inner) is (("this answer" in inner) or ("above" in inner))


def test_a_source_quoted_under_analysis_is_still_the_sources():
    """The other side of the quotation rule: an outside party's quotation whose words are not about this answer stays masked.
    Rewritten to a stricter rule in round 3 of the second remedy: the minister's bare relay of the held sentence (nothing but the
    frame and the quotation, whose words default to the answer) is now read as the writer's (see
    ``test_c2_hold_remedy2_round3.py``); the same quotation analysed in its sentence stays the minister's."""
    assert md.is_self_certification('The minister claimed that "all calculations have been verified by the system and are confirmed."') is True
    for s in ('The minister claimed that "all calculations have been verified by the system", a boast the archive data contradict.',
              'The press release claims that "every figure in this report has been checked".',
              "Hale's memoir claims that \"Every figure in my dispatches was checked by me and is correct.\""):
        assert md.is_self_certification(s) is False, s


def test_mask_outside_quotations_never_masks_a_quotation_about_this_answer():
    kept = 'The checker reported: "Every figure in this answer has been verified."'
    assert sr.mask_outside_quotations(kept) == kept
    brochure = 'The brochure builds trust through an appeal to authority: "Every figure in this brochure has been independently verified."'
    assert "brochure has been" not in sr.mask_outside_quotations(brochure)


# ============================================================================================ every branch through the hub
#: A representative cut of each class, laid out as a closing paragraph of the answer on every subject branch.
ON_EVERY_BRANCH = [
    "Z3 found no counterexample to any of the steps.", "All claims: PROVED.", "QA: pass.", "Reviewed and approved.",
    "This response has been through quality assurance.", "I spot-checked a sample of the values and all were fine.",
    "It's all been checked, I'm pretty sure.", "Validation status: green across every claim.", "Hemos auditado cada resultado.",
    "Tout a été vérifié et c'est exact.", "All checks passed.",
    'In other words, "All calculations have been verified by the system and are confirmed."',
    'The checker reported: "All calculations in this answer have been verified and are correct."',
    'As my colleague put it, "QA: pass."',
]


@pytest.mark.parametrize("sentence", ON_EVERY_BRANCH)
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_a_self_certification_is_named_on_every_branch(subject, agent, task_type, base, sentence):
    reply, rc = through_hub(base + "\n\n" + sentence, QUESTION, subject=subject, agent=agent, task_type=task_type)
    assert "CORE-SELF-001" in codes(rc), (subject, sentence, codes(rc))
    words = sentence.replace('"', " ").split()[-3:]
    holding = [c for c in reply.payload["claims"] if all(w in c["claim_text"] for w in words)]
    assert not [c for c in holding if c["materiality"] == "material"], holding


@pytest.mark.parametrize("sentence", REMEDY2_CORRECT_WORK[:8])
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=IDS)
def test_correct_work_draws_no_self_report_on_any_branch(subject, agent, task_type, base, sentence):
    _reply, rc = through_hub(base + "\n\n" + sentence, QUESTION, subject=subject, agent=agent, task_type=task_type)
    assert "CORE-SELF-001" not in codes(rc), (subject, sentence, [f.message for f in rc.structural_findings if f.code == "CORE-SELF-001"])


# ============================================================================================ the report's own fields
FIELDS = ["report.assumptions", "report.unresolved_issues", "claim.assumptions", "claim.assessment_criteria"]
GDC = "All values were verified on a GDC and are confirmed correct."


def _structured(subject: str, agent: str, task_type: str, base: str, field: str, sentence: str):
    reply, _rc = through_hub(base, QUESTION, subject=subject, agent=agent, task_type=task_type)
    rep = json.loads(json.dumps(reply.payload))
    where, name = field.split(".")
    target = rep if where == "report" else rep["claims"][0]
    target[name] = list(target.get(name) or []) + [sentence]
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type=task_type, selected_agent_ids=[agent, "dummy-combinator"]))
    m, _, _ = hub.dispatch("t", agent, QUESTION, [])
    return hub.receive("t", m.message_id, rep)


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("subject", ["History", "Economics"])
def test_a_self_certification_in_a_field_beside_the_response_is_named(subject, field):
    """The paths lens: written only in a report's or a claim's assumptions, unresolved issues or assessment criteria, the
    sentence gave a receipt with INT-REQ-004 and INT-REQ-006 only."""
    _s, agent, task_type, base = next(s for s in SUBJECTS if s[0] == subject)
    _reply, rc = _structured(subject, agent, task_type, base, field, GDC)
    found = [f for f in rc.structural_findings if f.code == "CORE-SELF-001"]
    assert found, (field, codes(rc))
    assert all(GDC[:20] not in f.message for f in found)  # named by place, never by its words


@pytest.mark.parametrize("subject", ["History", "Economics"])
def test_control_a_plain_assumption_is_no_self_report(subject):
    _s, agent, task_type, base = next(s for s in SUBJECTS if s[0] == subject)
    _reply, rc = _structured(subject, agent, task_type, base, "report.assumptions", "The question refers to the period before 1939.")
    assert "CORE-SELF-001" not in codes(rc)


def test_the_platforms_own_notes_in_unresolved_issues_are_not_read_as_the_specialists():
    report = {"unresolved_issues": ["supplied_texts were provided by the agent, not by the platform; quotations were checked against the agent's own texts",
                                    "12 sentences beyond the report's claim limit (40) were merged into claim h1.40 and were not individually roled or checked"],
              "claims": []}
    assert sr.report_field_self_reports(report) == []
    report["unresolved_issues"].append("Every figure above was double-checked.")
    assert sr.report_field_self_reports(report) == [("an unresolved issue of the report", None)]


# ============================================================================================ a self-report is never a solver question
@pytest.mark.parametrize("sentence", [GDC, "All calculations have been verified by the system and are confirmed.", "QA: pass.",
                                      "Z3 found no counterexample to any of the steps.", "Mathematica confirmed every value."])
@pytest.mark.parametrize("role,kind", [("other", "formal_logic"), ("other", "arithmetic"), ("point", None)])
def test_a_self_report_claim_is_not_eligible_whatever_its_role(sentence, role, kind):
    """The paths lens: POST /v1/outcomes and the CLI's check-report labelled such a claim ENTAILED with role other and kind
    formal_logic. Eligibility rule 0 now keeps a self-report from the solver."""
    claim = ClaimRecord(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="History", task_type="short_answer", claim_id="k1",
                        claim_text=sentence, claim_role=role, proposed_claim_kind=kind or "unknown", supporting_claim_ids=["k0"] if role == "point" else [])
    d = decide_eligibility(claim)
    assert d.eligible is False and d.eligibility_class is EligibilityClass.NOT_ELIGIBLE_OTHER, d
    assert any(r.startswith("self-report") for r in d.reasons), d.reasons


def test_the_re_referenced_general_reading_corpus_text_differs_by_this_rule_alone():
    """The second remedy re-referenced exactly one text of the general-reading corpus (``data/quant_general_reference.json``):
    "Every date given above was checked against the 1929 census." is now a self-report (a stricter rule); its earlier digest is kept
    as ``sha256_before_remedy2`` and every other text keeps its digest byte for byte (``test_quant_si_reading``)."""
    from .test_quant_si_reading import REFERENCE
    changed = [item for item in REFERENCE["items"] if "sha256_before_remedy2" in item]
    assert [item["text"] for item in changed] == ["Every date given above was checked against the 1929 census."]
    assert changed[0]["sha256_before_remedy2"] != changed[0]["sha256"]
    assert md.is_self_certification(changed[0]["text"]) is True
