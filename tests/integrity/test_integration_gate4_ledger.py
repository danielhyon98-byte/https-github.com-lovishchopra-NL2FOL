"""Integration gate 4: the claim ledger's readers (integrity/ledger.py).

Majors from the independent lenses (combinator faults, correctness), each with clean controls:

* a faithful synthesis that fronts the first event as a participial phrase ("Signed in March 1802, the Peace of Amiens broke
  down in May 1803.", "Having begun in 1914, the war ended in 1918.") was charged with re-pairing dates (INT-LEDGER-023):
  the pairing reader gave 'broke' (two tokens from 1802, four from 1803) to 1802 and the subject 'war' to 1914 alone. An
  event word between two figures of one kind now belongs to the statement on its side of the "and"
  (``ledger._own_conjunct``), and the subject two dated statements share stands with both dates (``_shared_subject``);
* a quantifier widened ("Some" -> "Most", "Many", a bare plural; "Most" -> "All", "Every"; "Half of" -> "Most") was not
  named (INT-LEDGER-026, ``_widened_quantifiers``);
* a comparative bound dropped ("more than twelve years" -> "twelve years", "over", "fewer than", "less than", "under",
  "above", "below", "upwards of", "in excess of") was not named (``_bound_before``);
* a view credited to the specialist who reported it, where the cited claim credits it to a colleague at its head ("The
  History specialist supplies the frame: ...") re-credited to the English specialist, was not named (``_credits_at_head``);
* a self-report in the ledger's own fields (a dropped entry's reason, a conflict's description or basis: "The overseer
  confirmed ...", "The Z3 engine proved ...", "Checked by the logic engine: ...") drew no INT-LEDGER-029, and the hub's
  INT-LEDGER-019 quoted such a reason as it stood (``ledger_field_self_reports``);
* a change restated as no change ("fell sharply" -> "continued unchanged", "stayed the same", "was unaffected") was not
  named (an opposed class of ``aligned_changes`` and ``no_change_differences``);
* an attributed view restated as fact ("Some historians argue that X" -> "X", "It is said that X" -> "X") was not named,
  under any transformation label (``dropped_attributions``).

The new readers are linear on the standard hostile inputs (runs of about 20,000 characters).
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.integrity import ledger as L
from epinoic_logic.integrity.contracts import ConflictRecord, LedgerEntry
from epinoic_logic.integrity.ledger import (
    check_synthesis_ledger, dropped_attributions, dropped_qualifiers, figure_pairing_differences, ledger_field_self_reports, meaning_differences,
    no_change_differences,
)
from epinoic_logic.ir.canonical import sha256_hex
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text


def _report(rid: str, agent: str, subject: str, claims: list[tuple[str, str, str]], certainty: str = "established") -> SpecialistReport:
    text = " ".join(t for _c, t, _r in claims)
    base = dict(request_id="req", task_id="task", report_id=rid, agent_id=agent, subject=subject, task_type="short_answer")
    return SpecialistReport(**base, original_response=text, response_sha256=sha256_text(text), created_at="2026-11-01T00:00:00Z",
                            claims=[ClaimRecord(**base, claim_id=c, claim_text=t, claim_role=r, materiality="material", certainty=certainty) for c, t, r in claims])


def _synthesis(reports: list[SpecialistReport], claims: list[tuple[str, str, list[str], str]], *, certainty: str = "established",
               ledger: tuple = (), conflicts: tuple = ()) -> Synthesis:
    sc = [SynthesizedClaim(claim_id=c, text=t, source_claim_ids=s, transformation=tr, certainty=certainty) for c, t, s, tr in claims]
    text = " ".join(c.text for c in sc)
    return Synthesis(synthesis_id="syn", request_id="req", task_id="task", combinator_agent_id="combinator", source_report_ids=[r.report_id for r in reports],
                     claims=sc, ledger=list(ledger), conflicts=list(conflicts), text=text, text_sha256=sha256_hex(text), created_at="2026-11-01T01:00:00Z")


def _codes(findings) -> list[str]:
    return sorted({f.code for f in findings})


# ======================================================================= dates paired with the verb of their own statement
AMIENS = "The Peace of Amiens was signed in March 1802 and broke down in May 1803."
WAR = "The war began in 1914 and ended in 1918."
TREATY = "The treaty was signed in 1919 and ratified in 1920."
FAITHFUL_PAIRINGS = [
    ("Signed in March 1802, the Peace of Amiens broke down in May 1803.", AMIENS),
    ("Having begun in 1914, the war ended in 1918.", WAR),
    ("The war ended in 1918, having begun in 1914.", WAR),
    ("Signed in 1919, the treaty was ratified in 1920.", TREATY),
    ("Having begun in 1914, the war lasted until 1918.", WAR),
    ("The war, which began in 1914, ended in 1918.", WAR),
    (AMIENS, AMIENS),
]
SWAPPED_PAIRINGS = [
    ("The war began in 1918 and ended in 1914.", WAR),
    ("Having begun in 1918, the war ended in 1914.", WAR),
    ("Signed in 1920, the treaty was ratified in 1919.", TREATY),
    ("Signed in May 1803, the Peace of Amiens broke down in March 1802.", AMIENS),
    ("The Peace of Amiens was signed in May 1803 and broke down in March 1802.", AMIENS),
]


@pytest.mark.parametrize("synthesis,source", FAITHFUL_PAIRINGS, ids=[s[:40] for s, _x in FAITHFUL_PAIRINGS])
def test_a_faithful_participial_or_coordinated_restatement_re_pairs_nothing(synthesis, source):
    assert figure_pairing_differences(synthesis, [source]) == []


@pytest.mark.parametrize("synthesis,source", SWAPPED_PAIRINGS, ids=[s[:40] for s, _x in SWAPPED_PAIRINGS])
def test_dates_moved_between_the_two_events_are_still_named(synthesis, source):
    found = figure_pairing_differences(synthesis, [source])
    assert found and any("(exchanged)" in d or "(re-paired)" in d for d in found), found


def test_an_event_word_after_and_belongs_to_the_second_statement():
    pairs, _kinds, _surface = L._figure_partners(AMIENS)
    assert ("1803", "w:brok") in pairs and ("1802", "w:brok") not in pairs, "'broke' is the verb of the 1803 event"
    pairs, _kinds, _surface = L._figure_partners(WAR)
    assert ("1918", "w:end") in pairs and ("1914", "w:end") not in pairs
    assert ("1914", "w:war") in pairs and ("1918", "w:war") in pairs, "the subject of both statements stands with both dates"
    # a second statement with a subject of its own shares none: the Ten Hours Act is 1847's, the Factory Act 1833's
    pairs, _kinds, _surface = L._figure_partners("The Factory Act of 1833 and the Ten Hours Act of 1847 limited hours.")
    assert ("1847", "w:ten") in pairs and ("1833", "w:ten") not in pairs and ("1847", "w:factory") not in pairs
    # a word with a figure on one side only keeps it
    pairs, _kinds, _surface = L._figure_partners("In 1939 Britain and France declared war.")
    assert ("1939", "w:franc") in pairs


def test_the_faithful_amiens_paraphrase_draws_no_int_ledger_023_through_the_ledger():
    rep = _report("rep-h", "history-specialist", "History", [("h1.1", AMIENS, "evidence")])
    good = check_synthesis_ledger([rep], _synthesis([rep], [("s1", "Signed in March 1802, the Peace of Amiens broke down in May 1803.", ["h1.1"], "paraphrased")]))
    assert "INT-LEDGER-023" not in _codes(good)
    bad = check_synthesis_ledger([rep], _synthesis([rep], [("s1", "Signed in May 1803, the Peace of Amiens broke down in March 1802.", ["h1.1"], "paraphrased")]))
    assert "INT-LEDGER-023" in _codes(bad)


# ======================================================================= quantifiers widened
FRAMED = "historians argue that the Peace of Amiens was only a truce."


def _cap(text: str) -> str:
    text = text.strip()
    return text[0].upper() + text[1:]


WIDENED = [("Some", "Most", "widens the quantifier 'Some'"), ("Some", "Many", "widens the quantifier 'Some'"), ("Some", "", "drops the quantifier 'Some'"),
           ("Some", "The", "drops the quantifier 'Some'"), ("Most", "All", "widens the quantifier 'Most'"), ("Many", "All", "widens the quantifier 'Many'"),
           ("Many", "Most", "widens the quantifier 'Many'"), ("Several", "Most", "widens the quantifier 'Several'"), ("Half of", "Most", "widens the quantifier 'Half of'"),
           ("Some", "All", "reverses the scope of a quantity"), ("Several", "All the", "reverses the scope of a quantity"),
           ("A minority of", "Most", "reverses a minority or a majority")]


@pytest.mark.parametrize("source,synthesis,said", WIDENED, ids=[f"{a}->{b or 'bare'}" for a, b, _s in WIDENED])
def test_a_widened_quantifier_is_named(source, synthesis, said):
    found = meaning_differences(_cap(f"{synthesis} {FRAMED}"), [_cap(f"{source} {FRAMED}")], "paraphrased")
    assert any(said in d for d in found), found
    assert len([d for d in found if "quantifier" in d or "scope of a quantity" in d or "minority" in d]) == 1, "one description per exchange"


def test_a_majority_made_universal_is_named_in_other_shapes():
    assert any("widens the quantifier 'Most'" in d for d in meaning_differences("Every historian argues that the Peace of Amiens was only a truce.",
                                                                                 ["Most historians argue that the Peace of Amiens was only a truce."], "paraphrased"))
    assert any("widens the quantifier 'Most'" in d for d in meaning_differences("All observers agreed the plan failed.", ["Most observers agreed the plan failed."], "paraphrased"))


KEPT_QUANTIFIERS = [
    ("Some historians argue that the Peace of Amiens was only a truce.", "Some historians argue that the Peace of Amiens was only a truce."),
    ("Some historians argue that the Peace of Amiens was only a truce.", "That the Peace of Amiens was only a truce is argued by some historians."),
    ("Most historians argue that the Peace of Amiens was only a truce.", "Many historians argue that the Peace of Amiens was only a truce."),
    ("Many historians argue that the Peace of Amiens was only a truce.", "Some historians argue that the Peace of Amiens was only a truce."),
    ("Some historians argue that the Peace of Amiens was only a truce.", "Two historians argue that the Peace of Amiens was only a truce."),
    ("Many workers left the land after 1850.", "Workers left the land in large numbers after 1850."),
    ("For some time the plan was popular with most voters.", "For some time the plan was popular with most voters."),
    ("Some 9,000 banks failed.", "Some 9,000 banks failed."),
]


@pytest.mark.parametrize("source,synthesis", KEPT_QUANTIFIERS, ids=[s[:40] for s, _x in KEPT_QUANTIFIERS])
def test_a_kept_narrowed_or_counted_quantifier_is_not_named(source, synthesis):
    assert meaning_differences(synthesis, [source], "paraphrased") == []


# ======================================================================= comparative bounds dropped
BOUNDS = ["more than", "over", "fewer than", "less than", "under", "above", "below", "upwards of", "in excess of"]


@pytest.mark.parametrize("bound", BOUNDS)
def test_a_dropped_comparative_bound_is_named_and_a_kept_one_is_not(bound):
    source = f"The drain had run for {bound} 12 years."
    found = meaning_differences("The drain had run for 12 years.", [source], "paraphrased")
    assert any(f"give '{bound} 12'" in d and "the bound is dropped" in d for d in found), found
    assert meaning_differences(source, [source], "paraphrased") == []


@pytest.mark.parametrize("synthesis,source", [
    ("The closure ended a drain that had run for twelve years.", "The closure ended a drain that had run for more than twelve years."),
    ("3 million people left.", "Over 3 million people left."),
    ("300 people left.", "Fewer than 300 people left."),
    ("The rate was 10 per cent.", "The rate was less than 10 per cent."),
    ("It took two weeks.", "It took under two weeks."),
])
def test_the_reported_bound_shapes_are_named(synthesis, source):
    assert any("the bound is dropped" in d for d in meaning_differences(synthesis, [source], "paraphrased"))


@pytest.mark.parametrize("synthesis,source", [
    ("More than 3 million people left.", "Over 3 million people left."),
    ("Binary search needs 20 comparisons.", "Binary search needs 20 comparisons, far fewer than the 1,000 of linear search."),
    ("Linear search needs 1,000 comparisons.", "Binary search needs 20, far fewer than 1,000."),
    ("The drain had run for 12 years.", "The drain had run for well over 12 years."),
    ("The loan was repaid in 10 years.", "The loan was repaid over 10 years."),
    ("Output reached 1913 levels.", "Output rose above 1913 levels."),
])
def test_a_comparison_a_period_or_a_year_is_no_dropped_bound(synthesis, source):
    assert not any("the bound is dropped" in d for d in meaning_differences(synthesis, [source], "paraphrased"))


def test_just_over_stays_an_approximation_named_once():
    found = meaning_differences("6 million were unemployed.", ["Just over 6 million were unemployed."], "paraphrased")
    assert any("the approximation is dropped" in d for d in found) and not any("the bound is dropped" in d for d in found)


# ======================================================================= a view credited to the specialist who reported it
H6 = "The closure therefore dealt with the exit rather than the reasons people left, and the flow fell sharply once the route was sealed."
S7 = 'The History specialist supplies the frame: the closure "dealt with the exit rather than the reasons people left".'
S9 = 'Its timetable is consistent with the History specialist\'s "Over the following weeks the barbed wire gave way to concrete".'


def _p7c():
    hi = _report("rep-hi", "history-specialist", "History", [("h1.6", H6, "point")], certainty="probable")
    lit = _report("rep-lit", "english-a-literature-specialist", "English A: Literature", [("p1-s07", S7, "interpretation"), ("p1-s09", S9, "interpretation")],
                  certainty="probable")
    return [hi, lit]


def _credit_findings(text: str, cite: str) -> list[str]:
    reps = _p7c()
    found = check_synthesis_ledger(reps, _synthesis(reps, [("s1", text, [cite], "paraphrased")], certainty="probable"))
    return [f.message for f in found if f.code == "INT-LEDGER-026"]


def test_the_history_specialists_words_re_credited_to_the_english_specialist_are_named():
    [message] = _credit_findings(S7.replace("History specialist", "English specialist"), "p1-s07")
    assert "credits the view to ['english-a-literature-specialist']" in message and "state the view of ['history-specialist']" in message


@pytest.mark.parametrize("text,cite", [
    (S7, "p1-s07"),
    ("According to the History specialist, the closure dealt with the exit rather than the reasons people left.", "p1-s07"),
    ("The English specialist finds the poem's timetable consistent with the History specialist's \"Over the following weeks the barbed wire gave way to "
     "concrete\".", "p1-s09"),
])
def test_the_faithful_credit_and_a_credit_inside_a_claim_are_not_named(text, cite):
    assert _credit_findings(text, cite) == []


def test_a_claim_that_opens_with_its_credit_holds_the_colleagues_view_only():
    assert L._credits_at_head(S7, ["history-specialist"])
    assert L._credits_at_head("According to the History specialist, X.", ["history-specialist"])
    assert L._credits_at_head("In the History specialist's view, X.", ["history-specialist"])
    assert not L._credits_at_head(S9, ["history-specialist"])
    assert not L._credits_at_head("The Company regulated river labour, bearing out the English specialist's claim.", ["english-specialist"])


# ======================================================================= self-reports in the ledger's own fields
TA2 = "The Peace of Amiens was signed in March 1802."
TB2 = "The Peace of Amiens was signed in October 1801."


def _two_dates():
    a = _report("rep-a", "history-specialist", "History", [("h1.1", TA2, "evidence")])
    b = _report("rep-b", "history-specialist-b", "History", [("h2.1", TB2, "evidence")])
    return [a, b]


SELF_REPORTS = ["The overseer confirmed the March 1802 date, so the October date was removed.",
                "The overseer confirmed the emigration total, so the note is no longer needed.",
                "Checked by the logic engine: both are verified and agree.",
                "The Z3 engine proved that March 1802 is correct.",
                "The engine found the two dates inconsistent.",
                "According to the overseer, the March date is right.",
                "Verified by Z3."]
NOT_SELF_REPORTS = ["The steam engine found wide use in the mills, which the question does not ask about.",
                    "Superseded by the History specialist's fuller account.",
                    "The dates differ: March 1802 against October 1801.",
                    "The History specialist checks the date against the treaty's text, and the dossier confirms it.",
                    "The overseer has not confirmed the date.",
                    "The plantation overseer is mentioned only in this sentence."]


@pytest.mark.parametrize("text", SELF_REPORTS)
def test_a_check_result_in_a_ledger_field_is_a_self_report(text):
    assert ledger_field_self_reports(text) == [text]


@pytest.mark.parametrize("text", NOT_SELF_REPORTS)
def test_a_reason_or_a_check_credited_to_a_specialist_is_no_self_report(text):
    assert ledger_field_self_reports(text) == []


def test_a_dropped_reason_that_reports_a_verdict_is_named_and_int_ledger_019_says_so():
    reps = _two_dates()
    reason = "The overseer confirmed the March 1802 date, so the October date was removed."
    syn = _synthesis(reps, [("s1", TA2, ["h1.1"], "carried")], ledger=(LedgerEntry(source_claim_ids=["h2.1"], transformation="dropped", reason=reason),))
    found = check_synthesis_ledger(reps, syn)
    [own] = [f for f in found if f.code == "INT-LEDGER-029"]
    assert own.severity == "warning" and own.claim_ids == ["h2.1"] and own.agent_ids == ["combinator"]
    assert "its recorded reason states a check result" in own.message and reason in own.message and "only a signed engine result is" in own.message
    [dropped] = [f for f in found if f.code == "INT-LEDGER-019"]
    assert reason in dropped.message and "the reason states a check result, a self-report" in dropped.message
    plain = _synthesis(reps, [("s1", TA2, ["h1.1"], "carried")],
                       ledger=(LedgerEntry(source_claim_ids=["h2.1"], transformation="dropped", reason="The October date is the preliminary peace, not the treaty."),))
    found = check_synthesis_ledger(reps, plain)
    assert "INT-LEDGER-029" not in _codes(found) and "self-report" not in next(f for f in found if f.code == "INT-LEDGER-019").message


def test_a_conflict_description_or_basis_that_reports_a_verdict_is_named_with_the_conflict():
    reps = _two_dates()
    conflict = ConflictRecord(conflict_id="k1", claim_ids=["h1.1", "h2.1"], description="Checked by the logic engine: both are verified and agree.",
                              status="resolved_with_basis", basis="The Z3 engine proved that March 1802 is correct.")
    syn = _synthesis(reps, [("s1", TA2, ["h1.1"], "carried"), ("s2", TB2, ["h2.1"], "carried")], conflicts=(conflict,))
    named = [f for f in check_synthesis_ledger(reps, syn) if f.code == "INT-LEDGER-029"]
    assert len(named) == 2 and all(f.severity == "warning" and f.claim_ids[:3] == ["k1", "h1.1", "h2.1"] for f in named)
    assert any("conflict record k1" in f.message and "its description states a check result" in f.message and "Checked by the logic engine" in f.message for f in named)
    assert any("conflict record k1" in f.message and "its basis states a check result" in f.message and "The Z3 engine proved" in f.message for f in named)
    clean = ConflictRecord(conflict_id="k1", claim_ids=["h1.1", "h2.1"], description="The reports give different dates.", status="resolved_with_basis",
                           basis="The October date is the preliminary peace; the treaty itself was signed in March 1802.")
    syn = _synthesis(reps, [("s1", TA2, ["h1.1"], "carried"), ("s2", TB2, ["h2.1"], "carried")], conflicts=(clean,))
    assert "INT-LEDGER-029" not in _codes(check_synthesis_ledger(reps, syn))


# ======================================================================= a change restated as no change
CHANGE = "Emigration fell sharply after 1961."


@pytest.mark.parametrize("synthesis", ["Emigration was unaffected after 1961.", "Emigration continued unchanged after 1961.", "Emigration stayed the same after 1961.",
                                       "Emigration continued after 1961.", "Emigration held steady after 1961.", "Emigration remained the same after 1961.",
                                       "After 1961, emigration was unaffected by the closure of the route."])
def test_a_change_restated_as_no_change_is_named(synthesis):
    found = meaning_differences(synthesis, [CHANGE], "paraphrased")
    assert any("a change or its absence" in d or "it states no change" in d for d in found), found


@pytest.mark.parametrize("synthesis", ["Emigration continued to fall after 1961.", "Emigration continued falling after 1961.", "Emigration dropped sharply after 1961.",
                                       "After 1961 emigration fell sharply."])
def test_a_change_kept_is_not_read_as_no_change(synthesis):
    assert meaning_differences(synthesis, [CHANGE], "paraphrased") == []


def test_the_p7c_flow_restated_as_unchanged_is_named_and_a_source_stating_no_change_itself_is_not_read():
    for edit in ("the flow continued unchanged", "the flow stayed the same"):
        assert any("a change or its absence" in d for d in meaning_differences(H6.replace("the flow fell sharply", edit), [H6], "paraphrased"))
    assert meaning_differences(H6.replace("fell sharply", "continued to fall"), [H6], "paraphrased") == []
    supply = "With supply unchanged, the price of one krona in US dollars rises from P1 to P2."
    assert no_change_differences("Demand for the krona shifts right while supply is unchanged.", [supply]) == []


# ======================================================================= an attributed view restated as fact
DROPPED_FRAMES = [
    ("The Peace of Amiens was only a truce.", "Some historians argue that the Peace of Amiens was only a truce.", "drops the attribution 'Some historians argue that'"),
    ("The war was caused by railway timetables.", "Taylor argues that the war was caused by railway timetables.", "drops the attribution 'Taylor argues that'"),
    ("The king fled at night.", "It is said that the king fled at night.", "drops the attribution 'It is said that'"),
    ("The war was caused by railway timetables.", "According to Taylor, the war was caused by railway timetables.", "drops the attribution 'According to Taylor,'"),
    ("Taylor shows that the war was caused by railway timetables.", "Taylor argues that the war was caused by railway timetables.", "states as shown ('shows that')"),
]


@pytest.mark.parametrize("transformation", ["paraphrased", "narrowed", "merged", "generalized", "carried"])
@pytest.mark.parametrize("synthesis,source,said", DROPPED_FRAMES, ids=[s[:30] for _y, s, _x in DROPPED_FRAMES])
def test_an_attributed_view_stated_as_fact_is_named_under_every_label(synthesis, source, said, transformation):
    found = meaning_differences(synthesis, [source], transformation)
    assert any(said in d for d in found), found


@pytest.mark.parametrize("synthesis,source", [
    ("According to some historians, the Peace of Amiens was only a truce.", "Some historians argue that the Peace of Amiens was only a truce."),
    ("Taylor contends that the war was caused by railway timetables.", "Taylor argues that the war was caused by railway timetables."),
    ("In Taylor's view, the war was caused by railway timetables.", "Taylor argues that the war was caused by railway timetables."),
    ("The war was caused by railway timetables, Taylor argues.", "Taylor argues that the war was caused by railway timetables."),
    ("The king is said to have fled at night.", "It is said that the king fled at night."),
    ("The war was expected to be over by Christmas.", "Many people believed that the war would be over by Christmas."),
    ("The war was caused by railway timetables.", "I argue that the war was caused by railway timetables."),
    ("The war was caused by railway timetables.", "This essay argues that the war was caused by railway timetables."),
])
def test_a_kept_frame_or_the_writers_own_frame_is_not_named(synthesis, source):
    assert dropped_attributions(synthesis, [source]) == []


def test_the_narrowed_channel_shape_is_named_through_the_ledger():
    rep = _report("rep-h", "history-specialist", "History", [("h1.1", "Some historians argue that the Peace of Amiens was only a truce.", "evidence")], certainty="possible")
    found = check_synthesis_ledger([rep], _synthesis([rep], [("s1", "The Peace of Amiens was only a truce.", ["h1.1"], "narrowed")], certainty="possible"))
    [f] = [f for f in found if f.code == "INT-LEDGER-026"]
    assert "drops the attribution 'Some historians argue that'" in f.message


# ======================================================================= the new readers are linear on hostile input
_HOSTILE = {"blanks": " ", "tabs": "\t", "breaks": "\n", "stops": ". ", "closing": ")", "labels": "(A1) ", "parens": "(", "brackets": "[",
            "fences": "```", "number words and": "twenty and ", "dates and verbs": "1914 and ended ", "= links": "= ", "list markers": "\n1. ",
            "groups": "some historians ", "frames": "Taylor argues that ", "continued": "continued ", "over": "over 1 ", "check names": "the overseer ",
            "quantifiers": "most of the ", "credits": "The History specialist ", "commas": ", ", "dated clauses": "in 1914, "}
_SOURCE = "Taylor argues that the war began in 1914 and ended in 1918, and some historians say emigration fell sharply."


@pytest.mark.parametrize("name", sorted(_HOSTILE))
def test_the_new_readers_take_linear_time_on_hostile_input(name):
    unit = _HOSTILE[name]
    text = (unit * (20_000 // len(unit) + 1))[:20_000] + "x"
    start = time.perf_counter()
    for call in (lambda: figure_pairing_differences(text, [_SOURCE]), lambda: figure_pairing_differences(_SOURCE, [text]),
                 lambda: dropped_qualifiers(text, [_SOURCE]), lambda: dropped_qualifiers(_SOURCE, [text]),
                 lambda: dropped_attributions(text, [_SOURCE]), lambda: dropped_attributions(_SOURCE, [text]),
                 lambda: no_change_differences(text, [_SOURCE]), lambda: no_change_differences(_SOURCE, [text]),
                 lambda: ledger_field_self_reports(text)):
        call()
    assert time.perf_counter() - start < 12.0, name  # about 1 s on the gate machine


def test_a_clause_of_many_quantified_groups_is_read_in_linear_time():
    """The widening rule read the source clause's keys again for every quantifier in it (quadratic); it reads them once."""
    def spent(n: int) -> float:
        src = ("some historians " * (n // 16))[:n] + "argue that the war was over."
        syn = ("most historians " * (n // 16))[:n] + "argue that the war was over."
        start = time.perf_counter()
        assert dropped_qualifiers(syn, [src])
        return time.perf_counter() - start
    small, large = spent(5_000), spent(40_000)
    assert large < 8.0 and large < 16 * small + 1.0  # eight times the text, never sixty-four times the work
