"""The outcome of a revision (design section 53; ``feedback.revision_outcome``): each fed-back flaw fixed, removed (allowed
or not), evaded, persisted or not re-checked, decided from the revision's receipt and a fresh task audit, never from the
specialist's words; the flaws introduced and the claims lost; the bounded loop with repeated-fault suppression and signed
escalations; and consolidation, where a superseded original gives way to its revision."""
from __future__ import annotations

from epinoic_logic.api.ir import SourceRef
from epinoic_overseer import feedback as F

from .conftest import EN_CLAIMS, EN_TEXT, english_report
from .feedback_support import INVENTED, PH_GOOD, english_case, physics_case


def _buckets(out) -> dict[str, str]:
    return {f.code: f.bucket for f in out.flaws}


# ============================================================================================ the buckets
def test_a_corrected_arithmetic_slip_is_fixed():
    case = physics_case()
    try:
        issue = case.ask()
        assert issue.allowed and [(f.code, f.rule, f.params) for f in issue.revision.flaws] == [("INT-SUBJ-001", "calc.does_not_hold", {"computed": "5", "stated": "6"})]
        a2, rc2 = case.deliver(issue, PH_GOOD, report_id="rep-ph-2")
        assert {f.code for f in rc2.findings} == {"INT-HANDOFF-009"}  # the correction propagates to the restatement: no preservation finding
        out = case.hub.revision_outcome(case.task_id, a2.message_id)
        assert _buckets(out) == {"INT-SUBJ-001": "fixed"} and out.next == "done" and out.introduced == [] and out.claims_lost == []
        assert F.verify_record(out, case.auditor.keyring)
    finally:
        case.close()


def test_an_invented_quotation_replaced_by_the_texts_own_words_is_fixed():
    case = english_case()
    try:
        issue = case.ask()
        fixed = dict(INVENTED, claim_text='The foreman says "We work until the bell".', source_refs=[SourceRef(document_id="doc-mill", excerpt="We work until the bell")])
        a2, _rc2 = case.deliver(issue, english_report(EN_TEXT + ' The foreman says "We work until the bell".', EN_CLAIMS + [fixed], report_id="rep-en-2"),
                                report_id="rep-en-2")
        out = case.hub.revision_outcome(case.task_id, a2.message_id)
        assert _buckets(out) == {"INT-REQ-003": "fixed"} and out.next == "done"
    finally:
        case.close()


def test_the_same_words_without_their_quotation_marks_are_removed_and_the_removal_is_allowed():
    case = english_case()
    try:
        issue = case.ask()
        plain = dict(INVENTED, claim_text="The foreman says they never rest at all.", source_refs=[])
        a2, _rc2 = case.deliver(issue, english_report(EN_TEXT + " The foreman says they never rest at all.", EN_CLAIMS + [plain], report_id="rep-en-2"),
                                report_id="rep-en-2")
        out = case.hub.revision_outcome(case.task_id, a2.message_id)
        f = out.flaws[0]
        assert (f.bucket, f.removal_ok, f.removal_allowed) == ("removed", True, True)
    finally:
        case.close()


def test_a_deleted_calculation_is_removed_not_allowed_and_its_claim_is_lost():
    case = physics_case()
    try:
        issue = case.ask()
        a2, _rc2 = case.deliver(issue, "The trolley starts from rest, so u = 0. The acceleration is therefore 5.0 m s⁻².", report_id="rep-ph-2")
        out = case.hub.revision_outcome(case.task_id, a2.message_id)
        f = out.flaws[0]
        assert (f.bucket, f.removal_ok, f.removal_allowed) == ("removed", False, False) and "s1.2" in out.claims_lost
    finally:
        case.close()


def test_a_calculation_turned_into_an_estimate_is_evaded():
    case = physics_case()
    try:
        issue = case.ask()
        a2, _rc2 = case.deliver(issue, "The trolley starts from rest, so u = 0. Using a = Δv/Δt, a is about 6 m s⁻². "
                                       "The acceleration is therefore 6.0 m s⁻².", report_id="rep-ph-2")
        out = case.hub.revision_outcome(case.task_id, a2.message_id)
        assert _buckets(out) == {"INT-SUBJ-001": "evaded"}
    finally:
        case.close()


def test_the_same_error_reworded_persists_and_the_chain_escalates():
    case = physics_case()
    try:
        issue = case.ask()
        a2, rc2 = case.deliver(issue, "The trolley starts from rest, so u = 0. With a = Δv/Δt we get a = (20 - 0)/4.0 = 6.0 m s⁻². "
                                      "The acceleration is therefore 6.0 m s⁻².", report_id="rep-ph-2")
        assert "INT-SUBJ-001" in {f.code for f in rc2.findings}
        out = case.hub.revision_outcome(case.task_id, a2.message_id)
        assert _buckets(out) == {"INT-SUBJ-001": "persisted"} and out.next == "escalated" and out.escalation_reason == "repeated_after_feedback"
        esc = case.hub.revisions(case.task_id)["escalations"]
        assert len(esc) == 1 and esc[0].reason == "repeated_after_feedback" and esc[0].finding.code == "OVS-FB-002" and F.verify_record(esc[0], case.auditor.keyring)
        again = case.ask(a2.message_id)
        assert not again.allowed and again.reason == "escalated" and len(case.hub.revisions(case.task_id)["escalations"]) == 1
        resp = case.hub.consolidate(case.task_id, request_message_ids=[case.m.message_id, issue.message.message_id])
        assert a2.message_id in resp.excluded_message_ids()  # its receipt carries the error again
    finally:
        case.close()


def test_a_fault_kept_verbatim_is_a_repeated_fault_of_the_same_agent_and_never_delivered():
    from .feedback_support import PH_BAD
    case = physics_case()
    try:
        issue = case.ask()
        a2, _rc2 = case.deliver(issue, PH_BAD, report_id="rep-ph-2")  # the very answer again, under a new report id
        out = case.hub.revision_outcome(case.task_id, a2.message_id)
        reps = case.hub.repeats(case.task_id).for_message(a2.message_id)
        assert reps and all(r.same_agent and r.code == "INT-SUBJ-001" for r in reps) and set(out.repeat_signatures) == {r.signature for r in reps}
        assert _buckets(out) == {"INT-SUBJ-001": "persisted"} and out.next == "escalated"
        resp = case.hub.consolidate(case.task_id, request_message_ids=[case.m.message_id, issue.message.message_id])
        ex = next(e for e in resp.excluded if e.message_id == a2.message_id)
        assert ex.repeated and "OVS-REP-001" in ex.codes
        nxt = case.ask(a2.message_id)
        assert not nxt.allowed and nxt.reason == "escalated"
    finally:
        case.close()


def test_a_rejected_revision_is_not_rechecked_and_escalates():
    case = physics_case()
    try:
        issue = case.ask()
        a2, rc2 = case.deliver(issue, PH_GOOD, report_id="rep-ph-1")  # the report id of its chain: INT-HANDOFF-018, not delivered
        assert a2 is None and "INT-HANDOFF-018" in {f.code for f in rc2.findings}
        out = case.hub.revision_outcome(case.task_id, rc2.message_id)
        assert _buckets(out) == {"INT-SUBJ-001": "not_rechecked"} and out.next == "escalated" and out.escalation_reason == "revision_not_delivered"
        resp = case.hub.consolidate(case.task_id, request_message_ids=[case.m.message_id, issue.message.message_id])
        orig = next(e for e in resp.excluded if e.message_id == case.a.message_id)
        assert not any("superseded" in r for r in orig.reasons)  # a REJECTED revision leaves the original as it was
    finally:
        case.close()


def test_a_new_invented_quotation_is_introduced_and_a_second_round_may_follow():
    case = english_case()
    try:
        issue = case.ask()
        new = dict(INVENTED, claim_id="en-ev4", claim_text='The children say "the mill never sleeps".',
                   source_refs=[SourceRef(document_id="doc-mill", excerpt="the mill never sleeps")])
        a2, _rc2 = case.deliver(issue, english_report(EN_TEXT + ' The children say "the mill never sleeps".', EN_CLAIMS + [new], report_id="rep-en-2"),
                                report_id="rep-en-2")
        out = case.hub.revision_outcome(case.task_id, a2.message_id)
        assert [i.code for i in out.introduced] == ["INT-REQ-003"] and out.next == "revise_again"
        second = case.ask(a2.message_id)
        assert second.allowed and second.round == 2 and second.revision.original_request_message_id == case.m.message_id
        assert [c.claim_id for f in second.revision.flaws for c in f.claims] == ["en-ev4"]
    finally:
        case.close()


# ============================================================================================ budget and suppression
def test_the_third_round_escalates_with_the_budget_spent():
    case = english_case(budget=2)
    try:
        lines = {1: ("The owners boast", "our looms outrun the river"), 2: ("A widow at the gate mutters", "bread costs more than breath")}

        def invented(i: int):  # each round introduces a new invented quotation in an unrelated claim
            who, words = lines[i]
            return dict(INVENTED, claim_id=f"en-x{i}", claim_text=f'{who} "{words}".', source_refs=[SourceRef(document_id="doc-mill", excerpt=words)])
        first = case.ask()
        a2, _ = case.deliver(first, english_report(EN_TEXT, EN_CLAIMS + [invented(1)], report_id="rep-en-2"), report_id="rep-en-2")
        second = case.ask(a2.message_id)
        assert second.allowed and second.round == 2
        a3, _ = case.deliver(second, english_report(EN_TEXT, EN_CLAIMS + [invented(2)], report_id="rep-en-3"), report_id="rep-en-3")
        third = case.ask(a3.message_id)
        assert not third.allowed and third.reason == "budget_exhausted" and third.escalation is not None
        assert third.escalation.finding.code == "OVS-FB-002" and third.escalation.rounds_used == 2
    finally:
        case.close()


def test_a_fed_back_error_that_comes_back_refuses_the_next_round():
    case = physics_case()
    try:
        issue = case.ask()
        a2, _ = case.deliver(issue, "The trolley starts from rest, so u = 0. With a = Δv/Δt we get a = (20 - 0)/4.0 = 6.0 m s⁻². "
                                    "The acceleration is therefore 6.0 m s⁻².", report_id="rep-ph-2")
        nxt = case.ask(a2.message_id)  # without asking for the outcome first: the returned signature alone ends the chain
        assert not nxt.allowed and nxt.reason == "repeated_after_feedback" and nxt.escalation.reason == "repeated_after_feedback"
    finally:
        case.close()


def test_a_budget_above_the_hard_maximum_is_capped_and_zero_disables():
    for budget, want in ((10, 3), (1, 1), (0, None)):
        case = english_case(budget=budget)
        try:
            issue = case.ask()
            if want is None:
                assert not issue.allowed and issue.reason == "disabled"
            else:
                assert issue.allowed and issue.max_rounds == want
        finally:
            case.close()


# ============================================================================================ consolidation
def test_a_superseded_original_gives_way_to_its_clean_revision():
    case = english_case()
    try:
        issue = case.ask()
        a2, _ = case.deliver(issue, english_report(EN_TEXT, EN_CLAIMS, report_id="rep-en-2"), report_id="rep-en-2")
        resp = case.hub.consolidate(case.task_id, request_message_ids=[case.m.message_id, issue.message.message_id])
        orig = next(e for e in resp.excluded if e.message_id == case.a.message_id)
        assert f"superseded by its revision {a2.message_id}" in orig.reasons
        assert [g.canonical_message_id for g in resp.groups] == [a2.message_id] and resp.status != "CONFLICTING"
    finally:
        case.close()


def test_feedback_changes_no_receipt_status_or_clearance_of_the_original():
    case = english_case()
    try:
        before = case.hub.clearance(case.task_id, case.a.message_id).state
        receipt = case.rc.model_dump(mode="json")
        issue = case.ask()
        case.deliver(issue, english_report(EN_TEXT, EN_CLAIMS, report_id="rep-en-2"), report_id="rep-en-2")
        assert case.hub.clearance(case.task_id, case.a.message_id).state == before
        held = next(r for r in case.hub.channels[case.task_id].receipts if r.message_id == case.a.message_id)
        assert held.model_dump(mode="json") == receipt
    finally:
        case.close()
