"""Round-10 clearance (integrated round c3), handoff pass: the one self-report reader, both directions (overseer handoff 2 and 3;
the round's critical records on the mark-point tick, the class readings of assurance words and the composer's display rule).

* Rule model-marks: the tick (✔) the Physics knowledge base prescribes after each marking point of a Mode B model line (rule S26) is a
  mark annotation, not a verification label: ph-t16's "Model: A higher temperature ... rises ✔. Each molecule ... ✔. The force ... ✔"
  drew three CORE-SELF-001 warnings, two ENTAILED outcomes were displayed NOT_ELIGIBLE and the answer was barred from the
  overseer-selected fallback. The STEM parser leaves the tick out of the claim as it leaves out "[1]", the core pack and the gate read
  the answer with those ticks blanked. A tick after a point about checking, or outside a model line, stays a label.
* Subject content and an honest refusal are no self-reports: a subject's technical terms ("Cross-validation gives a better estimate of
  accuracy.") and a modal or hypothetical "would be unverified" in another clause than a negative quantifier (the c3 decline "None of
  these figures is in the case, and I have no source for them in this session, so any number I gave would be unverified ...").
* A miss: an internal checker's decision on the answer's items ("The hub has already decided every relation above: all hold.") is a
  self-report on every branch; bug 23's three phrasings stay named on the History and Economics branches.
* The composer: a success display withheld because the claim's own words claim a check has its own summary meaning, and the display
  rule is one exported function (``translate.outcome.claim_display_status``) the composer and the auditor apply.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters import self_report as SR
from epinoic_logic.adapters.markdown import is_self_certification

from ..channel.c3_core_support import C3, _deliver
from ..core_hostile import SHAPES, one, sweep

PH = C3["c3"]["specialists"]["ph-t16"]
#: The Physics knowledge base's own example of a Mode B model line (rule S26), and one with working.
KB_MODEL = ("Model: Fission releases fast neutrons ✔. They collide with nuclei of the moderator and lose kinetic energy until they are slow ✔. "
            "Slow neutrons are much more likely to cause fission of uranium-235 nuclei, so the chain reaction is sustained ✔.")
KB_WORKING = "Model: W = mgh = 12 × 9.8 × 3.0 = 353 J ✔ P = W/t = 353/4.0 = 88 W ✔"


# ------------------------------------------------------------------------------------------ rule model-marks

@pytest.mark.parametrize("text, marks", [(KB_MODEL, 3), (KB_WORKING, 2), (PH["response_text"], 7)])
def test_the_ticks_of_a_model_line_are_mark_annotations(text, marks):
    ranges = SR.model_mark_ranges(text)
    assert len(ranges) == marks and all(set(text[a:b].strip()) <= set("✓✔☑️") for a, b in ranges)
    blanked = SR.blank_model_marks(text)
    assert len(blanked) == len(text) and "✔" not in blanked.split("Model:", 1)[1].split("\n", 1)[0]
    assert not SR.label_self_report(text if text != PH["response_text"] else KB_MODEL) and not SR.claims_a_check(KB_MODEL)


@pytest.mark.parametrize("text", [
    "Model: I checked every value ✔.",                      # a tick after a point about checking
    "Model: All values verified ✔",
    "The treaty was signed in 1919 ✓.",                     # a tick outside a model line
    "Each molecule that hits a wall undergoes a larger change of momentum ✔.",
    "Answer: 15 km/h ✔",
])
def test_controls_a_tick_after_a_check_or_outside_a_model_line_stays_a_label(text):
    assert SR.label_self_report(text) or is_self_certification(text), text
    assert SR.claims_a_check(text), text


def test_ph_t16_draws_no_self_certification_and_its_model_claims_carry_no_tick():
    hub, _ch, reply, rc = _deliver(PH, None, None)
    hub.close()
    named = [f for f in list(rc.findings) + list(rc.structural_findings) if f.code in ("CORE-SELF-001", "INT-HANDOFF-006")]
    assert not named, [(f.code, f.claim_ids, f.message[:120]) for f in named]
    claims = {c["claim_id"]: c["claim_text"] for c in reply.payload["claims"]}
    for cid in ("s1.10", "s2.11", "s3.10", "s4.13", "s4.14", "s4.15"):
        assert "✔" not in claims[cid] and not SR.claims_a_check(claims[cid]), (cid, claims[cid])
    assert claims["s4.13"] == "Model: A higher temperature means faster molecules, so their mean kinetic energy rises."
    # every claim text is still read from the answer: the answer with its model marks left out holds it
    unmarked = "".join(ch for k, ch in enumerate(PH["response_text"]) if not any(a <= k < b for a, b in SR.model_mark_ranges(PH["response_text"])))
    assert all(t.split("\n")[0] in unmarked for t in claims.values())


def test_control_a_tick_on_a_claim_about_checking_in_a_model_line_is_still_named():
    text = PH["response_text"].replace("Model: A higher temperature means faster molecules", "Model: I checked that a higher temperature means faster molecules")
    hub, _ch, _reply, rc = _deliver(PH, None, text)
    hub.close()
    assert [f for f in list(rc.findings) + list(rc.structural_findings) if f.code == "CORE-SELF-001"]


# ------------------------------------------------------------------------------------------ subject content and a refusal

@pytest.mark.parametrize("text", [
    "Cross-validation gives a better estimate of accuracy.",
    "Overfitting means the model fits the training data closely but its validation accuracy falls.",
    "k-fold cross-validation reports the mean validation accuracy over the folds.",
    "None of these figures is in the case, and I have no source for them in this session, so any number I gave would be unverified and "
    "should not go into your answer.",
])
def test_subject_content_and_an_honest_refusal_are_no_self_reports(text):
    assert not is_self_certification(text) and not SR.claims_a_check(text) and not SR.label_self_report(text), text


@pytest.mark.parametrize("text", [
    "Cross-validation confirms every figure in this answer.",
    "No figure was left unchecked.",
    "None of these figures went unchecked.",
    "Not one value went unverified.",
])
def test_controls_a_check_of_the_answer_beside_a_technical_term_and_a_double_negation_are_named(text):
    assert is_self_certification(text), text


def test_the_c3_decline_is_delivered_as_content_with_no_self_report_finding():
    hub, _ch, reply, rc = _deliver(C3["c3"]["specialists"]["bm-t16"], None, None)
    hub.close()
    decline = [c for c in reply.payload["claims"] if c["claim_text"].startswith("None of these figures is in the case")]
    assert decline and decline[0]["claim_role"] != "other"
    assert not [f for f in list(rc.findings) + list(rc.structural_findings)
                if f.code in ("CORE-SELF-001", "INT-HANDOFF-006") and decline[0]["claim_id"] in f.claim_ids]


# ------------------------------------------------------------------------------------------ the miss, and bug 23 on two branches

PHRASINGS = ["The hub has already decided every relation above: all hold.", "The engine has settled each step here.",
             "All calculations have been verified by the system and are confirmed.", "All values were verified on a GDC and are confirmed correct.",
             "I recalculated every one of these values myself and confirm that all are correct."]


@pytest.mark.parametrize("text", PHRASINGS)
def test_an_internal_checkers_decision_and_bug_23s_phrasings_are_self_reports(text):
    assert is_self_certification(text) and SR.claims_a_check(text), text


@pytest.mark.parametrize("text", ["The court decided every case above on its merits.", "The engine has not decided every relation above.",
                                  "Whether the hub has decided every relation above is not stated here."])
def test_controls_an_outside_decider_or_a_negated_decision_is_no_self_report(text):
    # Rewritten for hold remedy c3b (rules selfcert-1): the private internal-decision reader of the deleted self_report internals is
    # gone; the one reader is asserted instead, on the whole sentence (stricter: no other reading of the sentence may gate it either).
    # Rule: a decision credited to an outside decider (a court), or a negated or questioned one, is no claim that the answer's items
    # were decided (boundary (b)).
    assert is_self_certification(text) is False and SR.claims_a_check(text) is False, text


CASES = {"History": ("history-specialist", "Explain why the Treaty of Versailles angered Germans.",
                     "The Treaty of Versailles was signed in 1919 and imposed reparations on Germany, which many Germans saw as a humiliation."),
         "Economics": ("economics-specialist", "Explain how a tariff affects the domestic price.",
                       "A tariff of $2 raises the domestic price from $10 to $12, so domestic consumers buy less of the good.")}


@pytest.mark.parametrize("subject", sorted(CASES))
@pytest.mark.parametrize("text", PHRASINGS[:1] + PHRASINGS[2:])
def test_the_history_and_economics_branches_name_each_phrasing(subject, text):
    agent, question, base = CASES[subject]
    item = {"task_id": "t-b23", "subject": subject, "agent_id": agent, "task_type": "short_answer", "question": question, "supplied_texts": [],
            "response_text": base + "\n\n" + text}
    hub, _ch, _reply, rc = _deliver(item, None, None)
    hub.close()
    codes = {f.code for f in list(rc.findings) + list(rc.structural_findings)}
    assert {"CORE-SELF-001", "INT-HANDOFF-006"} <= codes, (subject, text, sorted(codes))


# ------------------------------------------------------------------------------------------ the composer's display rule and summary

def test_a_withheld_self_report_has_its_own_summary_and_the_display_rule_is_one_function():
    from epinoic_logic.engine import SolverConfig, verify
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.translate.contracts import ClaimRecord, TranslationResult, TranslationStatus, sha256_text
    from epinoic_logic.translate.contracts import EligibilityClass, EligibilityDecision
    from epinoic_logic.translate.outcome import WITHHELD_SELF_REPORT_MEANING, claim_display_status, compose_outcome
    key = b"c3-handoff-composer-key-0123456789abcdef"
    text = "The speed is 15 km/h, and I have double-checked every figure in this answer."
    base = dict(request_id="r", task_id="t", report_id="rep", agent_id="physics-specialist", subject="Physics", task_type="short_answer")
    claim = ClaimRecord(**base, claim_id="s1.1", claim_text=text, claim_role="point", materiality="material")
    v = {"op": "var", "name": "v"}
    prob = Problem.model_validate({"problem_id": "p1", "request_id": "r", "claim_id": "s1.1", "query": "entailment",
                                   "symbols": [{"name": "v", "sort": "Int", "meaning": "the speed in km/h"}],
                                   "premises": [{"id": "P", "expr": {"op": "eq", "left": v, "right": {"op": "int", "value": "15"}},
                                                 "grounding": {"kind": "arithmetic_fact"}}],
                                   "conclusion": {"id": "C", "expr": {"op": "gt", "left": v, "right": {"op": "int", "value": "10"}}}})
    tr = TranslationResult(translation_id="tr1", request_id="r", claim_id="s1.1", report_id="rep", status=TranslationStatus.TRANSLATED, problem=prob,
                           eligibility=EligibilityDecision(eligibility_class=EligibilityClass.QUANTITATIVE_CLAIM, eligible=True, decided_by="deterministic",
                                                           policy_version="test"),
                           claim_text_sha256=sha256_text(text), translator_version="test", policy_version="test", created_at="2026-11-16T00:00:00Z")
    ver = verify(prob, SolverConfig(timeout_ms=3000, memory_max_mb=None), signing_key=key, key_id="t")
    out = compose_outcome(claim, tr, ver, signing_key=key, key_id="t")
    assert ver.status.value == "ENTAILED" and out.display_status.value == "NOT_ELIGIBLE"
    assert f"Status meaning: {WITHHELD_SELF_REPORT_MEANING}." in out.summary and "not a solver question under policy" not in out.summary
    assert claim_display_status(claim, tr, ver, key, "t") == (out.display_status, True)
    # control: the same claim without the self-report shows the engine's verdict, with the plain meaning
    plain = ClaimRecord(**base, claim_id="s1.1", claim_text="The speed is 15 km/h.", claim_role="point", materiality="material")
    tr2 = tr.model_copy(update={"claim_text_sha256": sha256_text("The speed is 15 km/h.")})
    out2 = compose_outcome(plain, tr2, ver, signing_key=key, key_id="t")
    assert out2.display_status.value == "ENTAILED" and claim_display_status(plain, tr2, ver, key, "t") == (out2.display_status, False)


# ------------------------------------------------------------------------------------------ hostile input

@pytest.mark.parametrize("shape", SHAPES)
def test_the_new_readers_are_linear_on_hostile_input(shape):
    def entries(text):
        yield "model marks", lambda: SR.model_mark_ranges("Model: " + text + " ✔")
        yield "model marks (ticks)", lambda: SR.blank_model_marks("Model: " + text.replace("x", "✔"))
        yield "label", lambda: SR.label_self_report("Model: " + text[:3990])
        yield "claims a check", lambda: SR.claims_a_check(text[:3990])
        # rewritten for hold remedy c3b: the private internal-decision and double-negation readers are deleted; the one reader reads
        # the same inputs, whole and uncut (stricter: every reading of the text, not one pattern)
        yield "internal decision", lambda: is_self_certification("The hub has decided " + text)
        yield "double negation", lambda: is_self_certification("None of the figures " + text)
        yield "domain terms", lambda: is_self_certification("Cross-validation " + text[:3990])

    assert not sweep(entries, texts=one(shape)), shape
