"""The hub's synthesis readers added for the combinator pre-build's third verification (V3-H1 to V3-L4), at the unit level.

The end-to-end cases, through the combinator's runner and the hub, are in ``tests/integration/test_combinator_subproject.py``
(section "verification round 3"). Here each reader is pinned on its own, with clean controls:

- ``report_notes``: the claims the delivery roled 'other' are notes, the folded tail of an oversized report is not, and a
  flagged self-report is one whatever its role;
- ``unit_differences``: a figure's unit, SI prefix, per cent or era changed is named; another spelling of the same unit,
  a value the sources also state without a unit and an approximate restatement are not;
- the qualifier readers: an irregular verb, a short claim, a frequency word, a bound and "Most" for "a minority";
- ``check_conflict_records``: a conflict record over claims the hub found no contradiction between is the combinator's
  own statement (INT-CONFLICT-006, info), one over a found contradiction is not;
- ``meaningful``: a transformation word or the drop restated is no reason;
- the labels: an engine credited with a verdict, a bracketed status mark and a whole-sentence self-assessment at delivery,
  a bracketed proof verdict and "no errors in this synthesis" in a synthesis only.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import is_self_certification, is_synthesis_self_certification, synthesis_label, verification_label
from epinoic_logic.integrity.contracts import ConflictRecord, Synthesis, SynthesizedClaim
from epinoic_logic.integrity.cross_check import check_conflict_records
from epinoic_logic.integrity.ledger import meaning_differences, meaningful, report_notes, unit_differences
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text


def _report(claims: list[tuple[str, str, str]], issues: tuple[str, ...] = ()) -> SpecialistReport:
    text = " ".join(t for _c, _r, t in claims)
    return SpecialistReport(report_id="rep-1", request_id="req-1", task_id="task-1", agent_id="history-specialist", subject="History",
                            task_type="short_answer", original_response=text, response_sha256=sha256_text(text), created_at="2026-10-17T10:00:00Z",
                            unresolved_issues=list(issues),
                            claims=[ClaimRecord(request_id="req-1", task_id="task-1", report_id="rep-1", agent_id="history-specialist", subject="History",
                                                task_type="short_answer", claim_id=cid, claim_text=t, claim_role=role, materiality="supporting" if role == "other" else "material",
                                                advisory_verification_status="self-certified in the response text" if t.startswith("Verified:") else None)
                                    for cid, role, t in claims])


def test_notes_are_the_claims_roled_other_except_the_folded_tail_and_a_flagged_self_report_is_one_whatever_its_role():
    report = _report([("h1.1", "point", "The Treaty of Versailles was signed in June 1919."),
                      ("h1.2", "point", "Verified: The constitution was adopted in August 1919."),
                      ("h2.1", "other", "Word count: 45."),
                      ("h.tail", "other", "Sentences beyond the limit, about the Ruhr in 1923.")],
                     issues=("12 sentences beyond the report's claim limit (512) were merged into claim h.tail and were not individually roled or checked",))
    notes, flagged = report_notes([report])
    assert set(notes) == {"h2.1"}, "the folded tail holds unread content, not a note"
    assert set(flagged) == {"h1.2"}
    notes, _flagged = report_notes([report], {"h2.1"})
    assert notes == {}, "a colliding claim id is resolved by no rule"


UNIT_CASES = [
    # (source, synthesis, named)
    ("The trolley travels at 15 m/s.", "The trolley travels at 15 km/h.", True),
    ("The trolley travels at 15 m/s.", "The trolley travels at 15 mph.", True),
    ("Its kinetic energy is 225 J.", "Its kinetic energy is 225 kJ.", True),
    ("Its mass is 2 kg.", "Its mass is 2 g.", True),
    ("The area is 45 square units.", "The area is 45 units.", True),
    ("Area = 12 cm².", "Area = 12 cm.", True),
    ("The reaction is run at 25 °C.", "The reaction is run at 25 K.", True),
    ("Exports fell by 30 percent.", "Exports fell by 30 points.", True),
    ("Exports fell by 30 percent.", "Exports fell by 30 percentage points.", True),
    ("Exports fell by 30 percent.", "Exports fell 30 times over.", True),
    ("Germany lost 13 percent of its territory.", "Germany lost 13 provinces.", True),
    ("A loaf cost 200 billion marks.", "A loaf cost 200 billion dollars.", True),
    ("It cost £5 million.", "It cost $5 million.", True),
    ("It took 5 years.", "It took 5 months.", True),
    ("Exports fell after 1929.", "Exports fell after 1929 BC.", True),
    ("Caesar crossed the Rubicon in 49 BC.", "Caesar crossed the Rubicon in 49.", True),
    # controls: another spelling of the same unit, the same unit, a value the sources also state without one
    ("The trolley travels at 15 m/s.", "The trolley travels at 15 m s⁻¹.", False),
    ("The trolley travels at 15 m/s.", "The trolley travels at 15 metres per second.", False),
    ("Its mass is 2 kg.", "Its mass is 2 kilograms.", False),
    ("a = 5.0 m s⁻²", "a = 5.0 m/s²", False),
    ("The concentration is 0.1 mol dm-3.", "The concentration is 0.1 mol dm⁻³.", False),
    ("Exports fell by 30 percent.", "Exports fell by 30%.", False),
    ("Exports fell by 30 percent.", "Exports fell by 30 per cent.", False),
    ("It cost £5 million.", "It cost 5 million pounds.", False),
    ("Caesar crossed the Rubicon in 49 BC.", "Caesar crossed the Rubicon in 49 BCE.", False),
    ("The speed rose from 15 to 20 m/s.", "The speed rose from 15 km/h to 20 m/s.", False),
    ("In 1919 a treaty was signed.", "In 1919 the treaty was signed.", False),
    ("A current of 2 A flows through the 6 V supply.", "A current of 2 A flows through the 6 V battery.", False),
    ("Unemployment reached 6 million in 1932.", "Unemployment reached 6 million as the depression deepened in 1932.", False),
    ("It took 5 years.", "It took five years.", False),
]


@pytest.mark.parametrize("source,synthesis,named", UNIT_CASES, ids=[s[:40] for _src, s, _n in UNIT_CASES])
def test_a_changed_unit_is_named_and_another_spelling_of_the_unit_is_not(source, synthesis, named):
    found = unit_differences(synthesis, [source])
    assert bool(found) == named, found


QUALIFIER_CASES = [
    ("Exports may have fallen by roughly 30 percent after 1929.", "Exports fell by roughly 30 percent after 1929.", "drops the hedge"),
    ("The crisis may have begun in 1929.", "The crisis began in 1929.", "drops the hedge"),
    ("The policy may have worked.", "The policy worked.", "drops the hedge"),
    ("American loans usually stabilised the currency.", "American loans stabilised the currency.", "a frequency or generality qualifier"),
    ("American loans usually stabilised the currency.", "American loans rarely stabilised the currency.", "reverses a frequency"),
    ("Unemployment reached at least 6 million in 1932.", "Unemployment reached 6 million in 1932.", "the bound is dropped"),
    ("Up to 30 percent of exports were lost.", "Thirty percent of exports were lost.", "the bound is dropped"),
    ("The war lasted at most four years.", "The war lasted four years.", "drops the bound"),
    ("Only a minority of deputies supported the plan in 1929.", "Most deputies supported the plan in 1929.", "reverses a minority or a majority"),
    ("A few deputies backed the Young Plan.", "Nearly all deputies backed the Young Plan.", "reverses a minority or a majority"),
]
QUALIFIER_CONTROLS = [
    ("The policy may have worked.", "The policy may have worked."),
    ("The policy may have worked.", "The policy of appeasement worked in the short term because the guarantees delayed the attack."),
    ("American loans usually stabilised the currency.", "American loans generally stabilised the currency."),
    ("Unemployment reached at least 6 million in 1932.", "Unemployment reached at least 6 million in 1932."),
    ("Wages rose by more than 10 percent.", "Wages rose by 10 percent."),  # a comparison, not a bound: its figure may be exact
    ("The most decisive factor was the crash of 1929.", "A few historians see the crash of 1929 as decisive."),  # a superlative, not a majority
    ("Most deputies supported the plan.", "Most deputies supported the plan."),
]


@pytest.mark.parametrize("source,synthesis,said", QUALIFIER_CASES, ids=[s[:40] for _src, s, _x in QUALIFIER_CASES])
def test_each_dropped_qualifier_is_read(source, synthesis, said):
    found = meaning_differences(synthesis, [source], "paraphrased")
    assert any(said in d for d in found), found


@pytest.mark.parametrize("source,synthesis", QUALIFIER_CONTROLS, ids=[s[:40] for _src, s in QUALIFIER_CONTROLS])
def test_a_qualifier_kept_or_a_comparison_is_not_read_as_dropped(source, synthesis):
    assert meaning_differences(synthesis, [source], "paraphrased") == []


def _synthesis(conflicts: list[ConflictRecord]) -> Synthesis:
    text = "The trolley's speed is 15 m/s. The treaty was signed in 1919."
    return Synthesis(synthesis_id="syn-1", request_id="req-1", task_id="task-1", combinator_agent_id="synthesis", source_report_ids=["rep-a"],
                     claims=[SynthesizedClaim(claim_id="s0", text="The trolley's speed is 15 m/s.", source_claim_ids=["a-1"], transformation="carried"),
                             SynthesizedClaim(claim_id="s1", text="The treaty was signed in 1919.", source_claim_ids=["h-1"], transformation="carried")],
                     conflicts=conflicts, text=text, text_sha256=sha256_text(text), created_at="2026-10-17T10:00:00Z")


def test_a_conflict_record_the_hub_found_no_contradiction_for_is_the_combinators_own_statement():
    found = [(frozenset({"a-1", "b-1"}), "r-1")]
    invented = _synthesis([ConflictRecord(conflict_id="k0", claim_ids=["s0", "s1"], description="the dates disagree", status="unresolved")])
    [f] = check_conflict_records(invented, found)
    assert (f.code, f.severity) == ("INT-CONFLICT-006", "info") and set(f.claim_ids) == {"a-1", "h-1"}, "a synthesized id stands for its sources"
    disclosed = _synthesis([ConflictRecord(conflict_id="k0", claim_ids=["a-1", "b-1"], description="the two speeds differ", status="unresolved")])
    assert check_conflict_records(disclosed, found) == []
    resolved = _synthesis([ConflictRecord(conflict_id="k0", claim_ids=["s0", "s1"], description="x", status="resolved_with_basis", basis="the 1919 census")])
    assert check_conflict_records(resolved, found) == [], "a resolved record is the basis rule's (INT-CONFLICT-003)"


@pytest.mark.parametrize("reason", ["carried", "Merged", "narrowed", "dropped", "omitted", "removed", "left out", "  excluded "])
def test_a_transformation_word_or_the_drop_restated_is_no_reason(reason):
    assert not meaningful(reason)


@pytest.mark.parametrize("reason", ["it repeats h1.1", "a note of the specialist, not a claim of the answer", "it answers another question"])
def test_a_reason_in_words_is_a_reason(reason):
    assert meaningful(reason)


@pytest.mark.parametrize("sentence", ["[OK]", "(OK)", "[PASS]", "Z3: proved.", "(Z3: proved)", "Z3: unsat", "SMT: sat", "Solver: verified.",
                                      "All claims hold.", "Every claim above holds.", "Everything here holds.", "Each step checks out."])
def test_a_status_label_or_a_self_assessment_is_a_self_certification_on_every_branch(sentence):
    assert is_self_certification(sentence) and is_synthesis_self_certification(sentence)


@pytest.mark.parametrize("sentence", ["OK. Let us look at the poem.", "The steam engine — proved reliable in the Crimean War.", "Z3 = {0, 1, 2} is a cyclic group.",
                                      "The engine was okay in 1850.", "All claims hold that the treaty was harsh.", "Hence the above holds for n = 2.",
                                      "The forward made a pass (a long one) to the wing.", "Most claims hold.", "The engine: built by Watt in 1776."])
def test_a_mention_of_ok_an_engine_or_holding_is_no_self_certification(sentence):
    assert not is_self_certification(sentence) and verification_label(sentence) is None


def test_a_status_label_on_content_is_a_label_and_a_proof_verdict_only_in_a_synthesis():
    assert verification_label("The treaty was signed in 1919 [OK].").position == "after"
    assert verification_label("[OK] The treaty was signed in 1919.").position == "before"
    assert verification_label("The treaty was signed in 1919 (Z3: proved).").position == "after"
    assert verification_label("The identity holds (proven).") is None, "a specialist's proof may close on 'proven'"
    assert synthesis_label("The identity holds (proven).").position == "after"
    assert synthesis_label("(proven)").position == "whole"
    assert synthesis_label("The theorem (proven by Euler) is used.") is None, "a proof credited to someone is no label"
    assert is_synthesis_self_certification("No errors were found in this synthesis.")
    assert is_synthesis_self_certification("This synthesis contains no errors.")
    assert not is_synthesis_self_certification("It is not true that no errors were found in this synthesis.")
    assert not is_self_certification("No errors were found in the synthesis of ammonia."), "on a specialist's branch the synthesis is content"
