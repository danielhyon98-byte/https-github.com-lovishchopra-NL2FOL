"""Repair round 2, the argument classes of the generalisation review and of the review's adversarial probes, each with its
positive and its clean control:

* affirming the consequent and denying the antecedent whose fact is one conjunct of a stated conjunction, or whose missing
  bridge is the inverse of another stated rule (ARG-AC-001, ARG-DA-001);
* the rule, the fact and the converse or inverse step packed into one premise ("if a plant gets light it grows, and this
  plant gets no light, and so it will not grow"): named as the same fallacy, while modus ponens packed the same way and a
  stated biconditional with no fact are not;
* a sample's finding stated of a wider whole, with or without the writer's link (ARG-HG-001); the cases looked at, or a
  random sample, are not;
* an equivocal bridge read by the closed sense table (ARG-EQ-002);
* premises that contradict each other are the engine's INCONSISTENT_PREMISES, never a circularity refusal by the
  translator (consistency before entailment), while a consistent restatement is still refused as circular (E112);
* a provider output that certifies itself and is refused for its form records its verification claim beside the refusal
  (E505), so the self-certification is named, not lost with the output.
"""
from __future__ import annotations

import json

from epinoic_logic.engine.runner import premises_inconsistent
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, TranslationStatus, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

from .test_argument_diagnostics import AND, B, CFG, IMP, NOT, P, V, codes, problem, run


# ------------------------------------------------------------------------------------------------------- converse and inverse
def test_affirming_the_consequent_with_the_fact_inside_a_conjunction_is_named():
    m = B(raise_="the central bank raised interest rates in May", up="the krona appreciated in May", infl="inflation fell in May")
    pr = problem([P("r", IMP(V("raise_"), V("up")), "if the central bank raises rates, the currency appreciates", kind="general_knowledge"),
                  P("e", AND(V("up"), V("infl")), "the krona appreciated by 4% and inflation fell", kind="task_setting")], V("raise_"), m)
    assert codes(run(pr)).get("ARG-AC-001") == "warning"
    control = problem([P("r", IMP(V("raise_"), V("up")), "if the central bank raises rates, the currency appreciates", kind="general_knowledge"),
                       P("e", AND(V("raise_"), V("infl")), "the bank raised rates and inflation fell", kind="task_setting")], V("up"), m)
    assert "ARG-AC-001" not in codes(run(control)) and "ARG-DA-001" not in codes(run(control))


def test_a_bridge_that_is_the_inverse_of_another_stated_rule_denies_the_antecedent():
    m = B(signed="the peace accord was signed", calm="the border stayed calm", troops="the army moved troops to the border")
    pr = problem([P("r1", IMP(V("signed"), V("calm")), "had the accord been signed, the border would have stayed calm"),
                  P("e", NOT(V("signed")), "the accord was not signed", kind="task_setting"),
                  P("r2", IMP(NOT(V("calm")), V("troops")), "unrest on the border led the army to move troops")], V("troops"), m)
    assert codes(run(pr)).get("ARG-DA-001") == "warning"
    control = problem([P("r1", IMP(NOT(V("signed")), NOT(V("calm"))), "without the accord the border would not stay calm"),
                       P("e", NOT(V("signed")), "the accord was not signed", kind="task_setting"),
                       P("r2", IMP(NOT(V("calm")), V("troops")), "unrest on the border led the army to move troops")], V("troops"), m)
    assert not {"ARG-DA-001", "ARG-AC-001"} & set(codes(run(control)))


PLANT = B(light="the plant gets light", grow="the plant grows")


def test_the_inverse_step_packed_with_its_rule_and_fact_in_one_premise_denies_the_antecedent():
    packed = AND(IMP(V("light"), V("grow")), NOT(V("light")), IMP(NOT(V("light")), NOT(V("grow"))))
    pr = problem([P("p1", packed, "if a plant gets light it grows, and this plant gets no light, and so it will not grow")], NOT(V("grow")), PLANT)
    assert codes(run(pr)).get("ARG-DA-001") == "warning"
    # labelled as subject knowledge and not marked as a stated rule: the shape is recorded at info, not charged
    gk = problem([P("p1", packed, "if a plant gets light it grows, this plant gets no light, and a plant without light does not grow",
                    kind="general_knowledge")], NOT(V("grow")), PLANT)
    assert codes(run(gk)).get("ARG-DA-001") == "info"


def test_the_converse_step_packed_with_its_rule_and_fact_affirms_the_consequent():
    packed = AND(IMP(V("light"), V("grow")), V("grow"), IMP(V("grow"), V("light")))
    pr = problem([P("p1", packed, "if a plant gets light it grows, and this plant grew, and so it got light")], V("light"), PLANT)
    assert codes(run(pr)).get("ARG-AC-001") == "warning"


def test_modus_ponens_packed_in_one_premise_and_a_stated_biconditional_are_no_fallacy():
    mp = problem([P("p1", AND(IMP(V("light"), V("grow")), V("light")), "if a plant gets light it grows, and this plant gets light")], V("grow"), PLANT)
    assert not {"ARG-DA-001", "ARG-AC-001"} & set(codes(run(mp)))
    both = problem([P("p1", AND(IMP(V("light"), V("grow")), IMP(NOT(V("light")), NOT(V("grow")))),
                      "a plant grows if it gets light and does not grow without light"),
                    P("e", NOT(V("light")), "this plant gets no light", kind="task_setting")], NOT(V("grow")), PLANT)
    assert not {"ARG-DA-001", "ARG-AC-001"} & set(codes(run(both)))


# ------------------------------------------------------------------------------------------------------- hasty generalisation
def test_a_sample_stated_of_a_wider_whole_is_hasty_with_or_without_the_writers_link():
    m = B(t1="the one transect walked across the dunes found no sand lizards", dunes="the dune system has no sand lizards")
    pr = problem([P("e", V("t1"), "the transect found no sand lizards", kind="quotation"),
                  P("l", IMP(V("t1"), V("dunes")), "the transect is representative of the dunes", kind="assumption")], V("dunes"), m)
    assert codes(run(pr)).get("ARG-HG-001") == "warning"
    m2 = B(s="three of the four shoppers asked prefer paper bags", w="shoppers in the city prefer paper bags")
    assert codes(run(problem([P("e", V("s"), "three of the four shoppers asked prefer paper bags", kind="quotation")], V("w"), m2))).get("ARG-HG-001") == "warning"


def test_the_cases_looked_at_or_a_random_sample_are_no_hasty_generalisation():
    m = B(s="three of the four shoppers asked prefer paper bags", w="most of the shoppers asked prefer paper bags")
    pr = problem([P("e", V("s"), "three of the four shoppers asked prefer paper bags", kind="quotation"),
                  P("l", IMP(V("s"), V("w")), "three of four is most", kind="specialist_inference")], V("w"), m)
    assert "ARG-HG-001" not in codes(run(pr))
    m2 = B(s="a random sample of 2,000 voters favoured the plan", w="voters in the country favour the plan")
    pr2 = problem([P("e", V("s"), "a random sample of 2,000 voters favoured the plan", kind="quotation"),
                   P("l", IMP(V("s"), V("w")), "the sample stands for the country", kind="assumption")], V("w"), m2)
    assert "ARG-HG-001" not in codes(run(pr2))


# ------------------------------------------------------------------------------------------------------- equivocation by the sense table
def test_a_bridge_between_the_two_senses_of_demand_is_equivocation():
    m = B(want="many commuters want a seat on the 7.40 train (desire)", eff="effective demand (willingness and ability to pay) for rail travel has risen",
          fare="rail fares will rise")
    pr = problem([P("e", V("want"), "hundreds of commuters want a seat"),
                  P("r", IMP(V("eff"), V("fare")), "higher effective demand raises the price", kind="general_knowledge")], V("fare"), m)
    assert codes(run(pr)).get("ARG-EQ-002") == "warning"
    m2 = B(inc="commuters' incomes rose by 6%", eff="effective demand (willingness and ability to pay) for rail travel has risen", fare="rail fares will rise")
    pr2 = problem([P("e", V("inc"), "incomes rose by 6%", kind="task_setting"),
                   P("r", IMP(V("eff"), V("fare")), "higher effective demand raises the price", kind="general_knowledge")], V("fare"), m2)
    assert "ARG-EQ-002" not in codes(run(pr2))               # a bridge with no second sense is the generic missing link (ARG-NS-002)


# ------------------------------------------------------------------------------------------------------- contradiction before circularity
def _translate(problem_obj: dict, text: str):
    obj = {"interpretation": {"reading": "as written", "glossary": [], "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None,
           "problem": problem_obj}
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="psychology-specialist", subject="Psychology", task_type="short_answer")
    support = ClaimRecord(**ids, claim_id="s", claim_text="The study compared recall before and after a night's sleep.", claim_role="evidence")
    claim = ClaimRecord(**ids, claim_id="c", claim_text=text, claim_role="point", materiality="material", supporting_claim_ids=["s"])
    full = f"{support.claim_text} {text}"
    report = SpecialistReport(**ids, original_response=full, response_sha256=sha256_text(full), claims=[support, claim], supplied_texts=[],
                              created_at="2026-10-23T10:00:00Z")
    return verify_claim(claim, report, Translator(FixtureTranslationProvider({"c": json.dumps(obj)}), config=CFG), config=CFG)


def _recall(premises):
    return {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
            "symbols": [{"name": "more", "sort": "Bool", "meaning": "the participants recalled more words after sleep"}],
            "premises": [{"id": pid, "expr": e, "label": lab, "grounding": {"kind": "general_knowledge", "certainty": "established"}}
                         for pid, e, lab in premises],
            "conclusion": {"id": "C", "expr": V("more"), "label": "The participants recalled more words after sleep."}}


def test_premises_that_contradict_each_other_reach_the_engine_as_inconsistent_not_as_a_circle():
    contradictory = _recall([("f1", V("more"), "the participants recalled more words after sleep"),
                             ("f2", NOT(V("more")), "they did not recall more words after sleep")])
    out = _translate(contradictory, "The participants recalled more words after sleep, and they did not recall more words after sleep.")
    assert out.translation.status is TranslationStatus.TRANSLATED and out.display_status is S.INCONSISTENT_PREMISES
    assert not any("E112" in d for d in out.translation.diagnostics)


def test_a_consistent_restatement_is_still_refused_as_circular():
    restated = _recall([("f1", V("more"), "the participants recalled more words after sleep")])
    out = _translate(restated, "The participants recalled more words after sleep.")
    assert out.translation.status is TranslationStatus.INVALID_FORMALIZATION and any("E112" in d for d in out.translation.diagnostics)


def test_the_consistency_reader_proves_only_a_contradiction():
    from epinoic_logic.ir.schema import Problem
    p = Problem.model_validate(_recall([("f1", V("more"), "x"), ("f2", NOT(V("more")), "y")]))
    q = Problem.model_validate(_recall([("f1", V("more"), "x")]))
    assert premises_inconsistent(p) is True and premises_inconsistent(q) is False
    assert premises_inconsistent(p, budget_ms=0) is False      # no budget decides nothing


# ------------------------------------------------------------------------------------------------------- a refused self-certifying output
def test_a_refused_output_that_certifies_itself_records_its_verification_claim():
    forged = _recall([("f1", V("more"), "the participants recalled more words after sleep")])
    forged["premises"][0]["grounding"]["verified"] = True
    forged["premises"][0]["verified"] = True                  # a field the IR does not hold: the problem is refused for its form
    out = _translate(forged, "The participants recalled more words after sleep.")
    assert out.translation.status is TranslationStatus.INVALID_FORMALIZATION
    assert any("E505" in d and "verified=true" in d for d in out.translation.diagnostics), out.translation.diagnostics
    plain = _recall([("f1", V("more"), "the participants recalled more words after sleep")])
    plain["premises"][0]["verified"] = True
    assert not any("E505" in d for d in _translate(plain, "The participants recalled more words after sleep.").translation.diagnostics)
