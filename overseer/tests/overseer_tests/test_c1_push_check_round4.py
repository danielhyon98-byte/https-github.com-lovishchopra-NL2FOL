"""Attack round 4 on condition 6b found flaws in the fix's OWN readers (``docs/DELIVERY.md`` 6b; ``overseer/non_material.py``,
``overseer/meta_notes.py``). Each is closed at its cause:

* rule layout's part-id slot after the STEM structure heads (given, data, known values, working, solution, method,
  calculations) was the STEM parser's own open slot of four letters or digits, so "Working (fine):", "Method (good):",
  "Data (true):", "Solution (done):", "Working ok:" and "Known good:" were read as layout and freed on every branch; it now takes
  only the parsers' own part-label grammar (one letter a to h, a roman numeral up to viii, or a number of one or two digits
  with an optional letter, in the parsers' brackets);
* rule source-list took words that name no source ("Sources: the examination paper's own answers.", "the extract's own
  lines", "the original lines of the extract", "the specialist's own analysis", "original and full"); it now takes only
  names the supplied texts give, the knowledge bases' fixed sources forms, locators and kind tags: no word of ownership,
  origin, extent or fidelity, no answer but the student's pasted one, no part of a source without its locator, a specialist
  only with a subject and an analysis only as a specialist's;
* the lead reader read look-alike letters as no lead ("N" and a Cyrillic о, a Greek Ν, small capitals, "Ṇ"): every lead and
  label is now read on the confusable skeleton of the text (Cyrillic, Greek, Armenian and Cherokee look-alikes, Latin small
  capitals, dotless letters, a letter with a diacritic as its base letter; NFKC first, so fullwidth and mathematical letters
  too), so a look-alike lead opens a block that must be read, and a lead or label only the skeleton reads frees nothing;
* rule layout read a run of markscheme codes ("(A1) (A1) (A1) (A1)", "(N2)", "(M1)(A1)", "  A1  A1") as layout: a code is
  the mark the answer awards its own working, so only a run of mark allocations is layout now;
* rule layout read the task's wording again for every block (the blocks times the task's length): it is read once per answer.

The claim channel was NOT attempted in round 4 (the main session's direction then): an assurance the branch's parser reads as
a claim of the answer (any role but ``other``) reaches no 6b reader. Every claim-channel input of attack round 4 was pinned as
a strict xfail test until attack round 5 (below) with its behaviour at the published base 16d5a4a (``data/meta_note_attack_round4.json``): on an answer
without a closing note it was FORMALLY CHECKED there too (pre-existing), and on an answer that carries a genuine closing note
the base withheld it, because that note's ES-META-001 blocked the formal path; rule meta-note frees such a note since the
clearance commit, which makes the channel reachable on note-carrying answers.

Attack round 5 (``test_c1_push_check_round5.py``): the delivery policy's rule ``unverified-claims`` narrows the claim channel (a
claim no signed engine result decides positively is refused), so the strict xfail tests of the claim channel here are real tests
of the refusal now; it does not close the channel: assurances inside or as verified or eligible claims stay open to the formal
path, and only condition 6d (rule ``formal-label-withheld``, attack round 6) keeps them off the label; the label tests count
every claim of the recorded answer clean (``_clean_recorded_claims``), not only its eligible material claims, and the Physics
fixture's answer is built without its supporting evidence claim, which no signed engine result decides. The two Physics inputs
glued INTO the claim the engine verifies are named by the same rule (a note lead and an emoji inside the claim).
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import pytest

from epinoic_logic.adapters.stem_specialist.parser import _STRUCTURE_HEAD_RE
from epinoic_logic.api.branches import RouterHub
from epinoic_logic.api.integrity import WorkPlan
from epinoic_overseer.delivery_policy import FORMAL_LABEL_REASON, DeliveryPolicy
from epinoic_overseer.meta_notes import (
    _CONFUSABLES, _LIST_DENY, _PURE_LOCATORS, _SOURCE_WORDS, SOURCE_LIST_RULE, lead_blocks, lead_starts, read_meta_paragraph,
    read_source_list, reader_text, skeleton, source_list_grounding, unread_lead_blocks,
)
from epinoic_overseer.non_material import (
    LAYOUT_LABEL_RE, LAYOUT_RULE, english_units, non_material_blocks, read_layout, task_wordings, unread_non_material_blocks,
)
from epinoic_logic.api.translate import SpecialistReport, SuppliedText, sha256_text

from .c1_texts import EN_T14, EN_T14_Q
from .growth import growth
from .timing import measure
from .conftest import CFG, KEY, make_auditor
from .delivery_support import (
    CONSOLIDATION_EXCLUDED, PHYSICS, QUESTION, FakeClock, Verifier, assert_label_withheld_only, assert_refused_beyond_the_label,
    physics_report, run_task,
)
from .test_c1_push_check_meta_note import (
    FURTHER_GENUINE, RECORDED_NOTES, TUNER, UNVERIFIED_REASON, _clean_every_claim, _clean_recorded_claims, _deliver, assert_claim_refusal,
)

ROUND4 = json.loads((Path(__file__).parent / "data" / "meta_note_attack_round4.json").read_text(encoding="utf-8"))
EN_INPUTS = ROUND4["en_t14"]
CLOSED = [r for r in EN_INPUTS if r["status"] == "closed"]
OPEN = [r for r in EN_INPUTS if r["status"] == "open"]
PHYSICS_TEXT = ROUND4["physics_text"]
PHYSICS_REPORT = ROUND4["physics_report"]
EARLIER_OPEN = ROUND4["earlier_open"]
TUNER_GROUNDING = source_list_grounding(TUNER.title, TUNER.author)
P4_END = "so that Femi's absence can seem temporary."
P5_END = "paste it here for feedback."
SOURCES_LINE = "Sources: The Tuner extract (supplied text)"
NON_MATERIAL_REASON = ("the answer carries text its branch's parser reads as no claim of the answer that is read neither as a note, nor as a "
                       "pure source list, nor as layout (rule non-material-text): ")
LEAD_REASON = ("the answer carries a block opened by a note or sources lead that is read neither as a note nor as a pure source list "
               "(rule lead-blocks): ")
SELF_REPORT_REASON = "the answer carries a self-report or a relayed check result no check established: "
#: The reasons of rules 6b: positions and rule names only, never a word of the answer.
_NM_ITEM = r"(?:paragraph \d+(?: line \d+)?(?: inside the line)?|the answer as a whole) \(rule [a-z-]+\)"
_LB_ITEM = r"(?:paragraph \d+(?: line \d+)?(?: inside the line)?|the answer as a whole) \((?:a (?:note|sources) lead|its leads): rule [a-z-]+\)"
NM_REASON_RE = re.compile(r"^" + re.escape(NON_MATERIAL_REASON) + _NM_ITEM + r"(?:, " + _NM_ITEM + r")*(?: and \d+ more)?$")
LB_REASON_RE = re.compile(r"^" + re.escape(LEAD_REASON) + _LB_ITEM + r"(?:, " + _LB_ITEM + r")*(?: and \d+ more)?$")
#: The xfail reason of the claim channel, as measured at the published base (``base_16d5a4a`` of each open row).
CLAIM_CHANNEL = ("round 9: the English parser reads the input as a claim of the answer (any role but other), which no 6b reader reads. At "
                 "the published base 16d5a4a, with every claim counted clean, it was FORMALLY CHECKED on en-t14 without its note and "
                 "WITHHELD on en-t14 with its note (that note's ES-META-001 blocked the formal path); rule meta-note frees the note since "
                 "the clearance commit, so the channel is reachable on note-carrying answers")


def _with(row: dict) -> str:
    """The recorded en-t14 answer with a round-4 input added in the form its lens added it."""
    form, t = row["form"], row["text"]
    if form == "append":
        return EN_T14 + "\n\n" + t
    if form == "end-of-paragraph-4":
        return EN_T14.replace(P4_END, P4_END + t)
    if form == "inside-last-sentence-of-paragraph-4":
        return EN_T14.replace(P4_END, P4_END[:-1] + t + ".")
    if form == "line-in-paragraph-4":
        return EN_T14.replace(P4_END, P4_END + "\n" + t)
    if form == "start-of-paragraph-5":
        return EN_T14.replace("\n\nNext step:", "\n\n" + t + "Next step:")
    if form == "end-of-paragraph-5":
        return EN_T14.replace(P5_END, P5_END + t)
    if form == "paragraph-before-sources":
        return EN_T14.replace("\n\nSources:", "\n\n" + t + "\n\nSources:")
    if form == "end-of-paragraph-1":
        return EN_T14.replace("small, repairable fault.", "small, repairable fault." + t)
    if form == "end-of-sources":
        return EN_T14 + t
    if form == "replace-sources":
        assert EN_T14.endswith(SOURCES_LINE)
        return EN_T14[: -len(SOURCES_LINE)] + t
    raise ValueError(form)


def _ids(rows):
    return [f"{r['lens'][:3]}-{r['group'][:8]}-{r['form'][:12]}-{i}-{r['text'][:24]}" for i, r in enumerate(rows)]


def _reasons(decision, prefix):
    return [r for r in decision.receipt.formal.reasons if r.startswith(prefix)]


# ============================================================================================ the data
def test_the_round_4_data_covers_every_input_of_the_three_lenses():
    """The bypass lens's 158 label-level inputs (39 'NB' with no mark after it, 14 look-alike leads, 16 lead words no reader
    read, 32 other leads, 35 plain-prose sentences, 22 inputs inside the answer), its 8 borderline inputs and its 83 literal
    inputs already refused; the regression lens's 18 labels with an evaluation word in the part-id slot (appended and on a line
    of paragraph 4), 5 bracketed ones and 4 source lists in place of en-t14's; the review lens's 14 label lines. 145 are claims
    of the answer for the English parser (the claim channel, open for round 9); every other one is closed."""
    assert len(EN_INPUTS) == 290 and len(CLOSED) == 145 and len(OPEN) == 145
    by_group: dict = {}
    for r in EN_INPUTS:
        by_group[(r["lens"], r["group"])] = by_group.get((r["lens"], r["group"]), 0) + 1
    assert by_group == {("bypass", "nb"): 39, ("bypass", "look"): 14, ("bypass", "nopunct"): 16, ("bypass", "otherlead"): 32, ("bypass", "plain"): 35,
                        ("bypass", "inside"): 22, ("bypass", "borderline"): 8, ("bypass", "literal"): 83, ("regression", "label-append"): 9,
                        ("regression", "label-line"): 9, ("regression", "bracket"): 5, ("regression", "sources"): 4, ("review", "label"): 14}
    assert {r["group"] for r in OPEN} == {"nb", "look", "nopunct", "otherlead", "plain", "inside"}
    assert [r["text"] for r in OPEN if r["group"] == "look"] == ["Notes\u0131: every quotation above holds, and not one of them is off."]
    assert len(QUOTED_LITERALS) == 3 and {r["group"] for r in QUOTED_LITERALS} == {"literal"}
    for r in EN_INPUTS:
        assert set(r) <= {"text", "form", "lens", "group", "status", "base_16d5a4a"}
        assert ("base_16d5a4a" in r) == (r["status"] == "open")


# ============================================================================================ the real path: closed
def test_with_every_claim_clean_the_recorded_en_t14_answer_is_refused_by_the_label_rule_alone(monkeypatch):
    """The counterfactual's control (as in the earlier rounds' files).

    Rewritten to the stricter rule after attack round 5 (rule ``unverified-claims``): "every claim counted clean" counted only
    the eligible material claims, and en-t14's supporting claims (its quotations and interpretation sentences) carried no
    outcome, which the label no longer allows; every claim of the recorded answer is now counted clean
    (``_clean_recorded_claims``), and a claim the input adds keeps its real outcome.

    Rewritten to the stricter rule ``formal-label-withheld`` (``docs/DELIVERY.md`` condition 6d, attack round 6): the policy
    never grants FORMALLY CHECKED in the round-8 release. Where this test pinned the label it now pins that the label rule is
    the formal path's ONLY reason (every other condition holds, as before); where it pinned the reasons of a refusal it pins
    them with the label rule's reason last.

    Renamed after the re-review of the c1 landing, from
    ``test_the_recorded_en_t14_answer_alone_reaches_the_label_with_every_claim_clean``; the rename left its assertions as rewritten above to the stricter rule
    (the round-9 clearance corrected 'unchanged' here): the
    old name stated the label, which rule ``formal-label-withheld`` (``docs/DELIVERY.md`` condition 6d) withholds."""
    _clean_recorded_claims(monkeypatch)
    _rc, _report, decision, _audit = _deliver(EN_T14)
    assert decision.mode == "withheld" and decision.receipt.formal.reasons == [FORMAL_LABEL_REASON], decision.receipt.formal.reasons
    assert_label_withheld_only(decision)


#: The three literal inputs written inside quotation marks: the quoted assurance is a quotation of no supplied text, so the
#: channel's receipt carries error-level findings and the consolidation excludes the answer before the formal path reads it
#: (refused already before round 4, by no rule of condition 6b).
QUOTED_LITERALS = [r for r in CLOSED if r["text"][:1] in "\"\u201c\u2018"]


@pytest.mark.parametrize("row", CLOSED, ids=_ids(CLOSED))
def test_every_round_4_input_the_rules_close_keeps_en_t14_off_the_label(monkeypatch, row):
    """The label-level counterfactual: en-t14 with every claim of the recorded answer counted clean (``_clean_recorded_claims``)
    reaches every condition of the formal path without the input (the label rule alone withholds it,
    ``test_with_every_claim_clean_the_recorded_en_t14_answer_is_refused_by_the_label_rule_alone``) and never with it; the
    reasons are the 6b rules' (rule non-material-text, rule lead-blocks or the self-report's), naming the block by position and rule only, and
    may also name a claim the input adds (rule unverified-claims, condition 6c, or condition 3). Each look-alike lead was
    FORMALLY CHECKED on the worktree round 4 attacked (the parser reads it as a claim; the lead reader now reads its skeleton),
    each evaluative label, markscheme-code run and wider source list too (rule layout and rule source-list freed them); the
    literal inputs were refused already and stay refused (the three written inside quotation marks, :data:`QUOTED_LITERALS`,
    by the consolidation, which excludes the answer for its receipt's error-level findings).

    Rewritten to the stricter rule after attack round 5 (rule ``unverified-claims``): "every claim counted clean" counted only
    the eligible material claims, and en-t14's supporting claims (its quotations and interpretation sentences) carried no
    outcome, which the label no longer allows; every claim of the recorded answer is now counted clean
    (``_clean_recorded_claims``), and a claim the input adds keeps its real outcome.

    Made stricter after the pre-commit review of the c1 landing (rule ``formal-label-withheld``, condition 6d, puts its reason
    on every formal path, so "not FORMALLY CHECKED, some reason given" held whatever the 6b rules did): the refusal must rest
    on a reason other than the label rule's, a 6b reason (:func:`assert_refused_beyond_the_label`), so the answer is never
    FORMALLY CHECKED without the label rule either; a quoted literal must be excluded by the consolidation. Measured on the
    landing: no input of this test is refused by the label rule alone.

    Made stricter again after the re-review of the c1 landing: the self-report reason (rules self-report-disclosed and
    meta-note) is no longer accepted as the reason a row rests on; with that reader switched off every row still has a
    reason of rule lead-blocks or rule non-material-text. The test catches the removal of both rules, not of one while the
    other also refuses the row."""
    _clean_recorded_claims(monkeypatch)
    _rc, report, decision, _audit = _deliver(_with(row))
    assert report.original_response == _with(row)
    reasons = decision.receipt.formal.reasons
    if row in QUOTED_LITERALS:
        assert decision.mode != "formally_checked" and len(reasons) == 2 and reasons[0] == CONSOLIDATION_EXCLUDED, reasons
        assert reasons[1].endswith("is excluded: its receipt carries error-level findings"), reasons
        return
    assert_refused_beyond_the_label(decision, (NON_MATERIAL_REASON, LEAD_REASON))
    for r in reasons:
        if r.startswith(NON_MATERIAL_REASON):
            assert NM_REASON_RE.match(r), r
        elif r.startswith(LEAD_REASON):
            assert LB_REASON_RE.match(r), r


@pytest.mark.parametrize("row", [r for r in CLOSED if r["group"] == "look"], ids=lambda r: r["text"][:20])
def test_a_look_alike_lead_is_named_by_rule_lead_blocks(monkeypatch, row):
    """The 13 look-alike leads the English parser reads as a material point: rule lead-blocks reads the skeleton ("Nоte:" is
    "Note:"), so the block is read by rule meta-note, which frees only a bare lead as written (rule note-form refuses it).

    Rewritten to the stricter rule after attack round 5 (rule ``unverified-claims``): "every claim counted clean" counted only
    the eligible material claims, and en-t14's supporting claims (its quotations and interpretation sentences) carried no
    outcome, which the label no longer allows; every claim of the recorded answer is now counted clean
    (``_clean_recorded_claims``), and a claim the input adds keeps its real outcome."""
    _clean_recorded_claims(monkeypatch)
    _rc, _report, decision, _audit = _deliver(_with(row))
    assert _reasons(decision, LEAD_REASON) == [LEAD_REASON + "paragraph 7 (a note lead: rule note-form)"], decision.receipt.formal.reasons


@pytest.mark.parametrize("row", [r for r in CLOSED if r["lens"] in ("regression", "review")], ids=lambda r: f"{r['form']}-{r['text'][:24]}")
def test_every_evaluative_label_and_wider_source_list_is_named_by_its_rule(monkeypatch, row):
    """The regression and review lenses' inputs: a label with an evaluation word in the part-id slot is named by rule
    non-material-text (no closed label of the parsers' sets: the reading of rule layout), a source list naming no source by
    rule source-list (both rule lead-blocks and rule non-material-text).

    Rewritten to the stricter rule after attack round 5 (rule ``unverified-claims``): "every claim counted clean" counted only
    the eligible material claims, and en-t14's supporting claims (its quotations and interpretation sentences) carried no
    outcome, which the label no longer allows; every claim of the recorded answer is now counted clean
    (``_clean_recorded_claims``), and a claim the input adds keeps its real outcome."""
    _clean_recorded_claims(monkeypatch)
    _rc, _report, decision, _audit = _deliver(_with(row))
    nm = _reasons(decision, NON_MATERIAL_REASON)
    assert len(nm) == 1, decision.receipt.formal.reasons
    if row["group"] == "sources":
        assert nm == [NON_MATERIAL_REASON + "paragraph 6 (rule source-list)"]
        assert _reasons(decision, LEAD_REASON) == [LEAD_REASON + "paragraph 6 (a sources lead: rule source-list)"]
    elif row["form"] == "line-in-paragraph-4":
        assert "paragraph 4 line 2 (rule " in nm[0], nm
    else:
        assert "paragraph 7 (rule " in nm[0] or "paragraph 7 line " in nm[0], nm


# ============================================================================================ the real path: the claim channel
@pytest.mark.parametrize("row", OPEN, ids=_ids(OPEN))
def test_round_4_claim_channel_inputs_are_refused_by_the_claim_rules(monkeypatch, row):
    """Recorded as open after round 4 (the main session's direction then): with every claim counted clean these reached the
    label until attack round 5 (:data:`CLAIM_CHANNEL` records their behaviour at the published base).

    Rewritten after attack round 5 from a strict xfail into a real test of the refusal (and renamed from
    ``..._are_open_for_round_9``): rule ``unverified-claims`` needs every claim of the answer to carry a positive outcome of a
    signed engine result; with every claim of the recorded answer counted clean, the claim the input adds or changes keeps its
    real outcome, so the answer is never FORMALLY CHECKED and the reasons name that claim by id (condition 3 for a material
    eligible claim, rule unverified-claims for any other)."""
    _clean_recorded_claims(monkeypatch)
    _rc, report, decision, _audit = _deliver(_with(row))
    if _named_by_the_one_reader(row):
        # rewritten to a stricter rule (hold-fix round 2 of the round-9 push-check hold on the c2 clearance commit): an input the
        # one self-report reader names ("Accuracy: 100%.") is no claim any more but a self-report, refused by the self-report rules
        assert decision.mode != "formally_checked" and any(r.startswith(SELF_REPORT_REASON) or "self-certification-gate" in r
                                                           for r in decision.receipt.formal.reasons), decision.receipt.formal.reasons
        return
    assert_claim_refusal(decision, report, row["text"])


def _named_by_the_one_reader(row) -> bool:
    from epinoic_logic.api.adapters import is_self_certification
    return is_self_certification(row["text"].split("\n\n")[-1].strip())


def now_a_self_report(added: str) -> bool:
    """Hold-fix round 3 of the round-9 push-check hold on the c2 clearance commit: whether the shared self-report reader now names
    an input it did not before (a correctness word said of the answer, a bare verdict: "There is nothing to fix in this answer,
    not a single slip.", "All good.", "..., and nothing above needs fixing.")."""
    from epinoic_logic.api.adapters import is_self_certification
    return is_self_certification(added.strip().split("\n\n")[-1].strip())


def assert_self_report_refusal(decision, report=None, added: str = "") -> None:
    """The refusal of an input the shared self-report reader names (rewritten to that stricter rule in hold-fix round 3): the
    answer is never FORMALLY CHECKED and is refused beyond the label rule, by rule self-report-disclosed (a reason naming the
    self-report code) or, where the self-report sits inside the verified claim, by the exclusion of the answer whose receipt
    names it at error level; a claim holding it carries the advisory status; no reason holds its words."""
    assert decision.mode != "formally_checked" and not decision.label.lower().startswith("formally checked")
    reasons = decision.receipt.formal.reasons
    assert any(r.startswith(SELF_REPORT_REASON) or "self-certification-gate" in r or " is excluded: " in r for r in reasons if r != FORMAL_LABEL_REASON), reasons
    if report is not None and added:
        probe = " ".join(added.split())[:20]
        holding = [c for c in report.claims if probe and probe in " ".join(c.claim_text.split())]
        assert all(c.advisory_verification_status is not None for c in holding), [(c.claim_id, c.claim_role) for c in holding]
    probe = " ".join(added.split())[:16]
    if len(probe) >= 12:
        assert all(probe not in r for r in reasons), reasons


def _visible(t: str) -> str:
    return " ".join(t.split())


@pytest.mark.parametrize("row", OPEN, ids=_ids(OPEN))
def test_every_open_round_4_input_is_a_claim_of_the_english_parser(row):
    """The record of the open class: the English parser reads the input (its last paragraph when it adds two) inside a unit of
    a role other than ``other``, so no 6b reader has its text: rule non-material-text and rule lead-blocks name nothing."""
    text = _with(row)
    ins = row["text"].split("\n\n")[-1].strip()
    probe = _visible(ins)[:14]
    units = [u for u in english_units(text) if probe and probe in _visible(u.text)]
    if _named_by_the_one_reader(row):
        # rewritten to a stricter rule (hold-fix round 2): an input the one self-report reader names is set aside as a self-report,
        # never read as a claim of the answer
        assert units and not any(u.claim for u in units), (row["text"], [(u.text[-60:], u.claim) for u in units])
        return
    assert units and any(u.claim for u in units), (row["text"], [(u.text[-60:], u.claim) for u in units])
    assert unread_non_material_blocks(text, english_units(text), grounding=TUNER_GROUNDING, task_wording=EN_T14_Q) == []
    assert unread_lead_blocks(text, TUNER_GROUNDING) == []


@pytest.mark.parametrize("row", OPEN, ids=_ids(OPEN))
def test_the_behaviour_of_each_open_round_4_input_at_the_published_base_is_recorded(row):
    """Measured on the published base 16d5a4a on the same real path, every claim counted clean (the data's ``base_16d5a4a``):
    on en-t14 as recorded WITHHELD (its own closing note's ES-META-001, which the base never freed, and the word bound the
    task's "about 250 words" sets, INT-REQ-005, which counted its sources line); on en-t14 shortened under that bound WITHHELD
    by the note's ES-META-001 alone;
    on the same without its note FORMALLY CHECKED, the capability predating rule meta-note. Two exceptions, each recorded: an
    input that adds a genuine note of its own is WITHHELD there by that note; an assurance written before "Next step:" makes the
    note paragraph body text for the base, so it was FORMALLY CHECKED even with the note.

    Recorded data, not a measurement: the ``base_16d5a4a`` figures were measured once on the published base 16d5a4a when the
    round was triaged and are stored in ``data/meta_note_attack_round4.json``; this test checks the data's shape and values and
    runs no delivery, so the suite does not re-measure them (this tree cannot run the base)."""
    base = row["base_16d5a4a"]
    assert base["en_t14"]["mode"] == "withheld" and "INT-REQ-005" in base["en_t14"]["codes"]
    if row["form"] == "start-of-paragraph-5":
        assert base["short_with_note"] == {"mode": "formally_checked", "codes": []} and base["noteless"] is None
        return
    assert base["short_with_note"] == {"mode": "withheld", "codes": ["ES-META-001"]}
    if row["text"].startswith("Note: I can't see the image.\n\n"):
        assert base["noteless"] == {"mode": "withheld", "codes": ["ES-META-001"]}
    else:
        assert base["noteless"] == {"mode": "formally_checked", "codes": []}


def test_the_claim_channel_inputs_of_rounds_2_and_3_have_their_base_behaviour_recorded():
    """The same measurement for the open inputs of attack rounds 2 (nine plain-prose ones) and 3 (59, and "NB all quotations
    hold."): each WITHHELD at the base on en-t14 with its note, FORMALLY CHECKED there without it. One round-3 open input, a
    look-alike lead ("Nоte:" with a Cyrillic о), is closed in round 4 (the worktree withholds it).

    Recorded data, not a measurement: the ``base_16d5a4a`` figures and the ``worktree_en_t14`` modes (of the worktree round 3 attacked) were measured once on the published base 16d5a4a when the
    round was triaged and are stored in ``data/meta_note_attack_round4.json``; this test checks the data's shape and values and
    runs no delivery, so the suite does not re-measure them (this tree cannot run the base)."""
    from .test_c1_push_check_lead_blocks import OPEN as OPEN2
    from .test_c1_push_check_non_material import CLOSED_IN_ROUND_4, NO_LEAD_ASSURANCES
    from .test_c1_push_check_non_material import OPEN as OPEN3
    rec = {(r["round"], r["text"], r["form"]): r for r in EARLIER_OPEN}
    want = [(2, r["text"], r["form"]) for r in OPEN2] + [(3, r["text"], r["form"]) for r in OPEN3 + CLOSED_IN_ROUND_4]
    want += [(3, t, "append") for t in NO_LEAD_ASSURANCES]
    assert sorted(want) == sorted(rec) and len(rec) == 9 + 59 + 1
    for key, r in rec.items():
        assert r["base_16d5a4a"] == {"en_t14": {"mode": "withheld", "codes": ["ES-META-001", "INT-REQ-005"]},
                                     "short_with_note": {"mode": "withheld", "codes": ["ES-META-001"]},
                                     "noteless": {"mode": "formally_checked", "codes": []}}, key
        assert r["worktree_en_t14"] == ("withheld" if r in [rec[(3, x["text"], x["form"])] for x in CLOSED_IN_ROUND_4] else "formally_checked")


# ============================================================================================ the Physics fixture, for real
def _physics_text(text: str):
    """The Physics delivery fixture's task answered with ``text`` delivered as text: the STEM parser builds the claims and the
    fixture verifier runs the engine on the quantitative ones (no counterfactual)."""
    clock = FakeClock()
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    try:
        plan = WorkPlan(plan_id="plan-task-dlv", selected_agent_ids=["physics-specialist"], **PHYSICS)
        ch = hub.open_task(plan)
        ch.verify_claim_fn = Verifier(clock)
        m, _req, rq = hub.dispatch(plan.task_id, "physics-specialist", QUESTION, [])
        assert m is not None, rq.findings
        session = DeliveryPolicy(clock=clock).start(hub, plan.task_id)
        session.install()
        reply, rc = hub.receive(plan.task_id, m.message_id, text, agent_id="physics-specialist", report_id="rep-1")
        assert reply is not None, rc
        return SpecialistReport.model_validate(reply.payload), session.decide(request_message_ids=[m.message_id], receipts={rc.message_id: rc})
    finally:
        hub.close()


def _physics_text_answer(row) -> str:
    base, extra = "The speed is 15 km/h.", row["added"]
    return base[:-1] + extra + "." if extra.startswith(";") else base + extra


#: The one control of the Physics text path the STEM parser reads as a claim of the answer: a part-labelled structure head is a
#: 'structural' supporting claim for it, which no signed engine result decides (rule ``unverified-claims``, attack round 5).
STRUCTURAL_CONTROL = "structural head b (control)"
#: The two claim-channel inputs of the Physics text path glued INTO the verified quantitative claim (the STEM parser reads the
#: result and the added words as one claim): that claim carries a positive outcome of a signed engine result, because the
#: fixture's translation is fixed and its fidelity review says "faithful" whatever the claim's words. Since attack round 5 rule
#: ``unverified-claims`` names such a claim when its text holds a note lead after a clause mark or a character outside the claim
#: alphabet (an emoji), the two cases here.
GLUED = ("inline semicolon note", "thumbs after result")
UNVERIFIED_ONLY = re.compile(r"^" + re.escape(UNVERIFIED_REASON) + r"s\d+\.\d+ \(supporting [a-z]+: not_[a-z]+\)$")


@pytest.mark.parametrize("row", [r for r in PHYSICS_TEXT if r["status"] in ("control", "closed")], ids=lambda r: r["name"])
def test_the_physics_answer_delivered_as_text_for_real(row):
    """No counterfactual: the answer "The speed is 15 km/h." is checked by the engine and FORMALLY CHECKED, with a genuine note
    too; the push check's sentence, a look-alike lead, a lead alone on its line and a markscheme code after the result (or a
    paragraph of them) are refused, named by the 6b rules.

    Rewritten to the stricter rule after attack round 5 (rule ``unverified-claims``): it pinned the label for the answer with a
    part-labelled structure head ("Working (b):"), which the STEM parser reads as a 'structural' supporting claim that no
    signed engine result decides; that answer is now refused by the new rule alone, naming the claim. The STEM parser reads a
    look-alike lead and a lead alone on its line as an analysis step too, so rule unverified-claims may name it beside the 6b
    rules.

    Rewritten to the stricter rule ``formal-label-withheld`` (``docs/DELIVERY.md`` condition 6d, attack round 6): the policy
    never grants FORMALLY CHECKED in the round-8 release. Where this test pinned the label it now pins that the label rule is
    the formal path's ONLY reason (every other condition holds, as before); where it pinned the reasons of a refusal it pins
    them with the label rule's reason last."""
    _report, decision = _physics_text(_physics_text_answer(row))
    assert decision.receipt.formal.reasons[-1] == FORMAL_LABEL_REASON, decision.receipt.formal.reasons
    reasons = decision.receipt.formal.reasons[:-1]
    if row["name"] == STRUCTURAL_CONTROL:
        assert decision.mode != "formally_checked" and len(reasons) == 1 and UNVERIFIED_ONLY.match(reasons[0]) and "structural" in reasons[0], reasons
        return
    if row["status"] == "control":
        assert decision.mode == "withheld" and reasons == [], reasons
        assert_label_withheld_only(decision)
        return
    assert decision.mode != "formally_checked" and not decision.label.lower().startswith("formally checked")
    # hold-fix round 3 (stricter): an input the shared self-report reader now names is also named a self-report on the receipt
    allowed = (NON_MATERIAL_REASON, LEAD_REASON, UNVERIFIED_REASON) + ((SELF_REPORT_REASON,) if now_a_self_report(row["added"]) else ())
    assert reasons and all(r.startswith(allowed) for r in reasons), reasons
    assert any(r.startswith((NON_MATERIAL_REASON, LEAD_REASON)) for r in reasons), reasons


@pytest.mark.parametrize("row", [r for r in PHYSICS_TEXT if r["status"] == "open" and r["name"] not in GLUED], ids=lambda r: r["name"])
def test_physics_text_claim_channel_inputs_are_refused_for_real(row):
    """No counterfactual. The STEM parser reads each input as a claim of the answer (an analysis step, a point, a 'structural'
    head through the parser's own open part-id slot). At the published base 16d5a4a this path was WITHHELD for every input (the
    base's translation checks named the quantitative claim, OVS-TRN-005); after the clearance commit each reached the label.

    Rewritten after attack round 5 from a strict xfail into a real test of the refusal (and renamed from
    ``..._are_open_for_round_9``): rule ``unverified-claims`` refuses the label, because the claim the input adds carries no
    positive outcome of a signed engine result, and names it by id; "LGTM." also turns the result into a point the verifier
    does not translate (condition 3 names it)."""
    report, decision = _physics_text(_physics_text_answer(row))
    if now_a_self_report(row["added"]):
        # rewritten to the stricter rule in hold-fix round 3: the shared self-report reader names the input, so the STEM parser sets
        # it aside as a self-report (role other, the advisory status) and rule self-report-disclosed refuses the answer
        assert_self_report_refusal(decision, report, row["added"].strip())
        return
    assert decision.mode != "formally_checked" and not decision.label.lower().startswith("formally checked")
    reasons = decision.receipt.formal.reasons
    added = [c.claim_id for c in report.claims if c.claim_role != "other" and c.claim_text != "The speed is 15 km/h."]
    assert added and any(r.startswith(UNVERIFIED_REASON) and any(f" {i} (" in " " + r[len(UNVERIFIED_REASON):] for i in added) for r in reasons), reasons


@pytest.mark.parametrize("row", [r for r in PHYSICS_TEXT if r["name"] in GLUED], ids=lambda r: r["name"])
def test_physics_text_inputs_glued_into_the_verified_claim_are_refused_for_real(row):
    """The input is glued INTO the quantitative claim (the STEM parser reads the result and the added words as one claim), and
    that claim carries a positive outcome of a signed engine result, because the fixture's translation is fixed and its
    fidelity review says "faithful" whatever the claim's words. At the published base 16d5a4a this path was WITHHELD for every
    input (OVS-TRN-005).

    Rewritten after attack round 5 from a strict xfail into a real test of the refusal (and renamed from
    ``..._are_open_for_round_9``): a claim carries the outcome of what was encoded, never of what is glued to it, so rule
    ``unverified-claims`` names a claim whose text holds a note lead after a clause mark ("; note: ...") or a character outside
    the claim alphabet (" 👍"). Words glued with neither stay the fidelity review's (``test_c1_push_check_round5.py``)."""
    _report, decision = _physics_text(_physics_text_answer(row))
    reasons = decision.receipt.formal.reasons
    assert decision.mode != "formally_checked", reasons
    assert any(r.startswith(UNVERIFIED_REASON) and ("s1.1 (quantitative: a note lead inside the claim)" in r
                                                   or "s1.1 (quantitative: a character outside the claim alphabet, U+1F44D)" in r) for r in reasons), reasons


@pytest.mark.parametrize("row", [r for r in PHYSICS_TEXT if r["status"] == "open"], ids=lambda r: r["name"])
def test_the_open_physics_text_inputs_are_claims_of_the_stem_parser_and_their_base_behaviour_is_recorded(row):
    """The STEM parser reads each open input as a claim of the answer (run on this tree).

    Recorded data, not a measurement: the ``base_16d5a4a`` figures were measured once on the published base 16d5a4a when the
    round was triaged and are stored in ``data/meta_note_attack_round4.json``; this test reads them from the data and
    runs no delivery at the base, so the suite does not re-measure them (this tree cannot run the base)."""
    report, _decision = _physics_text(_physics_text_answer(row))
    probe = _visible(row["added"]).lstrip(";")[:10].strip()
    if now_a_self_report(row["added"]):
        # hold-fix round 3 (stricter): the shared self-report reader names the input, so the STEM parser sets it aside (role other)
        assert all(c.claim_role == "other" and c.advisory_verification_status is not None for c in report.claims if probe in _visible(c.claim_text)), \
            [(c.claim_role, c.claim_text) for c in report.claims]
    else:
        assert any(c.claim_role != "other" and probe in _visible(c.claim_text) for c in report.claims), [(c.claim_role, c.claim_text) for c in report.claims]
    assert row["base_16d5a4a"] == {"mode": "withheld", "codes": ["OVS-TRN-005"]}


def test_the_physics_text_data_is_complete():
    """The Physics text rows of round 4 by status.

    Recorded data, not a measurement: the ``base_16d5a4a`` figures were measured once on the published base 16d5a4a when the
    round was triaged and are stored in ``data/meta_note_attack_round4.json``; this test checks the data's shape and values and
    runs no delivery, so the suite does not re-measure them (this tree cannot run the base)."""
    by = {s: [r["name"] for r in PHYSICS_TEXT if r["status"] == s] for s in ("control", "closed", "open", "not-decided")}
    assert len(by["control"]) == 3 and len(by["closed"]) == 6 and len(by["open"]) == 10 and by["not-decided"] == ["plain prose same line"]
    assert all(r["base_16d5a4a"]["mode"] == "withheld" for r in PHYSICS_TEXT)


def _physics_report(extra):
    """The Physics fixture's report object with ``extra`` added to its text, delivered for real. Since attack round 5 (rule
    ``unverified-claims``) the report is built without its supporting evidence claim, which no signed engine result decides
    (``physics_report(..., evidence=False)``)."""
    clock = FakeClock()
    rep = physics_report("physics-specialist", "rep-1", evidence=False)
    text = rep.original_response + "\n\n" + extra
    rep = rep.model_copy(update={"original_response": text, "response_sha256": sha256_text(text)})
    run = run_task(DeliveryPolicy(clock=clock), [("physics-specialist", rep)], verify=Verifier(clock))
    try:
        return run.decision
    finally:
        run.close()


@pytest.mark.parametrize("row", PHYSICS_REPORT, ids=lambda r: r["added"][:24])
def test_the_physics_report_object_for_real(row):
    """No counterfactual, the Physics fixture delivered as its report object (the regression and review lenses' path): text
    added that the report never claims is read by rule non-material-text. Each evaluative label line and markscheme-code run
    travelled FORMALLY CHECKED (rule layout read it); now each is refused. A part-labelled head, a run of mark allocations and
    a genuine note keep the label.

    Rewritten to the stricter rule after attack round 5 (rule ``unverified-claims``): the report held a supporting evidence
    claim no signed engine result decides, so it is built without it (:func:`_physics_report`); and the part-labelled head
    "Working (b):" is a 'structural' claim for the STEM parser that the report does not hold, so that answer is now refused by
    the new rule alone, naming the parser's claim. A run of mark allocations and a genuine note keep the label.

    Rewritten to the stricter rule ``formal-label-withheld`` (``docs/DELIVERY.md`` condition 6d, attack round 6): the policy
    never grants FORMALLY CHECKED in the round-8 release. Where this test pinned the label it now pins that the label rule is
    the formal path's ONLY reason (every other condition holds, as before); where it pinned the reasons of a refusal it pins
    them with the label rule's reason last."""
    decision = _physics_report(row["added"])
    if row["added"] == "Working (b):":
        assert decision.receipt.formal.reasons[-1] == FORMAL_LABEL_REASON, decision.receipt.formal.reasons
        reasons = decision.receipt.formal.reasons[:-1]
        assert decision.mode != "formally_checked" and len(reasons) == 1 and reasons[0].startswith(UNVERIFIED_REASON), reasons
        assert reasons[0].endswith("(structural: read by its branch's parser, held by no claim of the journaled report)"), reasons
        return
    if row["status"] == "control":
        assert decision.mode == "withheld" and decision.receipt.formal.reasons == [FORMAL_LABEL_REASON], decision.receipt.formal.reasons
        assert_label_withheld_only(decision)
        return
    assert decision.mode != "formally_checked" and decision.receipt.formal.reasons[-1] == FORMAL_LABEL_REASON
    nm = _reasons(decision, NON_MATERIAL_REASON)
    assert len(nm) == 1 and NM_REASON_RE.match(nm[0]) and "paragraph 2" in nm[0], decision.receipt.formal.reasons


# ============================================================================================ rule layout: the part id
#: Part ids the parsers' own grammar holds ("(b)", "b)", "(iii)", "(2)", "(2b)") after each STEM structure head.
PART_IDS = ["(a)", "(h)", "b)", "(i)", "(iv)", "(viii)", "(2)", "(12)", "(2b)", "3)"]
#: What the slot took before round 4 and no part-label grammar holds: an evaluation, a grade, a word, a code.
NOT_PART_IDS = ["(fine)", "(good)", "(true)", "(done)", "(ok)", "ok", "fine", "good", "best", "pass", "sure", "(ix)", "(A1)", "(z)", "(2 ok)", "(b) ok",
                "(okay)", "(neat)", "(tidy)", "(safe)", "(10/10)", "A", "(\u2713)", "( c )"]
STEM_HEADS = ["Given", "Data", "Known", "Known values", "Known data", "Known quantities", "Working", "Workings", "Solution", "Method", "Calculation",
              "Calculations"]


@pytest.mark.parametrize("head", STEM_HEADS)
def test_a_stem_structure_head_takes_only_the_parsers_part_label_grammar(head):
    for pid in PART_IDS:
        label = f"{head} {pid}:"
        assert read_layout(label).ok, label
        assert LAYOUT_LABEL_RE.fullmatch(label), label
    for pid in NOT_PART_IDS:
        label = f"{head} {pid}:"
        reading = read_layout(label)
        assert not reading.ok and reading.rule == LAYOUT_RULE, (label, reading)


def test_every_part_id_rule_layout_takes_is_one_the_stem_parser_reads_too():
    """Agreement with the parser: the STEM parser's own head pattern reads every part id rule layout takes (rule layout's slot is
    a subset of the parser's), so the narrowing refuses only what the parser's open slot alone would read."""
    for head in ("Working", "Solution", "Method", "Given", "Data"):
        for pid in PART_IDS:
            assert _STRUCTURE_HEAD_RE.match(f"{head} {pid}:".lower()), (head, pid)


@pytest.mark.parametrize("text", ["Working (fine):", "Method (good):", "Data (true):", "Solution (done):", "Working ok:", "Known good:",
                                  "Known values (good):", "Method OK:", "Calculations done:", "Method best:", "Working pass:", "Workings sure:",
                                  "**Method OK:**", "- Working fine:", "> Data true:", "Method OK:\nWorking fine:"])
def test_the_regression_and_review_lenses_label_lines_are_refused(text):
    assert not read_layout(text).ok
    blocks = [b for b in non_material_blocks(EN_T14 + "\n\n" + text, english_units(EN_T14 + "\n\n" + text), grounding=TUNER_GROUNDING,
                                             task_wording=EN_T14_Q) if not b.read]
    assert blocks and {b.paragraph for b in blocks} == {7}, blocks


# ============================================================================================ rule layout: markscheme codes
@pytest.mark.parametrize("text", ["(A1) (A1) (A1) (A1)", "(N2)", "(M1)(A1)", "  A1  A1", "AG", "(R1)", "M1 A1", "[2] A1", "(M1)(A1)(A1)", "A1 A1 AG",
                                  "[1] (A1)"])
def test_a_run_holding_a_markscheme_code_is_refused(text):
    reading = read_layout(text)
    assert not reading.ok and reading.rule == LAYOUT_RULE and reading.form and "markscheme code" in reading.detail, reading


@pytest.mark.parametrize("text", ["[2]", "[1 spare]", "[2 marks]", "(3 marks)", "[2] [1]", "[2] [2] [3]", "(a) [2]", "Part (b) [2 marks]"])
def test_a_run_of_mark_allocations_is_still_layout(text):
    assert read_layout(text).ok, text


def test_a_code_after_a_claim_is_named_by_rule_layout():
    """After the claim it follows, a markscheme code is its own block: rule layout names it (the code is a form it reads and
    refuses for what it holds)."""
    text = EN_T14.replace(P4_END, P4_END + " (A1)")
    unread = unread_non_material_blocks(text, english_units(text), grounding=TUNER_GROUNDING, task_wording=EN_T14_Q)
    assert [(b.paragraph, b.inline, b.rule) for b in unread] == [(4, True, LAYOUT_RULE)], unread


# ============================================================================================ rule source-list
#: The regression lens's and the bypass lens's lists that named no source, each refused by rule source-list.
NO_SOURCE = [
    "Sources: The Tuner extract (supplied text); the extract's own lines.", "Sources: the examination paper's own answers.",
    "Sources: The Tuner extract's own lines (supplied text).", "Sources: The Tuner extract (supplied text), the original lines of the extract.",
    "Sources: The Tuner extract (supplied text); the specialist's own analysis", "Sources: The Tuner extract (supplied text), original and full",
    "Sources: The Tuner extract (supplied text); the extract's lines", "Sources: the extract's lines 3 and the poem's lines",
    "Sources: your answer (supplied text)", "Sources: the answers", "Sources: The Tuner extract (supplied text); the full extract",
    "Sources: the specialist's analysis (supplied text)", "Sources: the extract analysis", "Sources: The Tuner extract, p.", "Sources: the textbook chapter",
    "Sources: The Tuner extract; the official markscheme", "Sources: the examiner's report", "Sources: The Tuner extract (supplied text), intact",
    "Sources: the actual extract", "Sources: the same extract", "Sources: the real extract", "Sources: The Tuner extract, unaltered",
    "Sources: your work (supplied text)", "Sources: the student's results (supplied text)", "Sources: the extract's title", "Sources: the poet",
    "Sources: The Tuner extract; the conversation",
]
#: The knowledge bases' fixed forms, locators and kind tags: still read.
KB_FORMS = [
    ("Sources: practice question (supplied text); your pasted answer (supplied text)", frozenset()),
    ("Sources: your question (supplied text); course notes (course notes)", frozenset()),
    ("Sources: the History specialist's context paragraph (supplied text)", frozenset()),
    ("Sources: Economics specialist's analysis (supplied text)", frozenset()),
    ("Sources: the Biology specialist's report (supplied text)", frozenset()),
    ("Sources: Biology course notes (course notes)", frozenset()), ("Sources: general Psychology course knowledge (course notes)", frozenset()),
    ("Sources: The Tuner extract, lines 3-5", TUNER_GROUNDING), ("Sources: Act IV, scene ii", frozenset()), ("Sources: The Tuner extract, p. 12", TUNER_GROUNDING),
    ("Sources: The Tuner extract, pp. 12-14.", TUNER_GROUNDING), ("Sources: Appendix A", frozenset()), ("Sources: Extracts A and B", frozenset()),
    ("Sources: The Tuner extract (paragraphs 1 and 2)", TUNER_GROUNDING), ("Sources: The Tuner extract (supplied text)", TUNER_GROUNDING),
]


@pytest.mark.parametrize("text", NO_SOURCE)
def test_a_list_naming_no_source_is_refused(text):
    reading = read_source_list(text, TUNER_GROUNDING)
    assert not reading.ok and reading.rule == SOURCE_LIST_RULE and reading.detail, (text, reading)


@pytest.mark.parametrize("text, grounding", KB_FORMS, ids=[t[:40] for t, _g in KB_FORMS])
def test_the_knowledge_bases_fixed_forms_locators_and_kind_tags_are_still_read(text, grounding):
    assert read_source_list(text, grounding).ok, read_source_list(text, grounding)


def test_the_closed_list_names_sources_only():
    """No word of ownership, origin, extent or fidelity, no answer but the pasted one, no work, results, student, title, heading,
    caption or person is in the closed list; the deny list holds the first four and the official answers; every part a locator
    names is in the closed list (it is read only with its locator)."""
    for w in ("own", "original", "full", "answers", "work", "results", "student", "student's", "students", "title", "titles", "heading", "headings",
              "caption", "captions", "author", "authors", "writer", "poet", "conversation"):
        assert w not in _SOURCE_WORDS, w
    for w in ("own", "original", "full", "answers", "official", "markscheme", "examiner", "intact", "unaltered", "actual", "real", "same"):
        assert w in _LIST_DENY, w
    assert _PURE_LOCATORS <= _SOURCE_WORDS and not (_SOURCE_WORDS & _LIST_DENY)


@pytest.mark.parametrize("row", [r for r in CLOSED if r["group"] == "sources" or (r["group"] == "borderline" and r["form"] == "end-of-sources")],
                         ids=lambda r: r["text"][:30])
def test_the_round_4_source_lists_are_refused_by_both_rules(row):
    text = _with(row)
    assert [(b.paragraph, b.kind, b.rule) for b in unread_lead_blocks(text, TUNER_GROUNDING)] == [(6, "sources", SOURCE_LIST_RULE)]


# ============================================================================================ the confusable skeleton
LOOK_ALIKE_LEADS = ["N\u043ete:", "\u039dote:", "\u0274ote:", "\u1e46ote:", "N\u03bfte:", "Not\u0435:", "N\u0412:", "\u039d.\u0392.", "N\u0435xt step:",
                    "C\u0430veat:", "\u0274\u1d0f\u1d1b\u1d07:", "Lim\u0456t:", "S\u043eurces:", "\u0405ources:", "\u039d\u039fTE:", "N\u0585te:"]


@pytest.mark.parametrize("lead", LOOK_ALIKE_LEADS)
def test_a_look_alike_lead_is_a_lead_and_frees_nothing(lead):
    """Read on the skeleton, each look-alike lead opens a block (the plain reading reads none), and no reader frees it: rule
    meta-note asks for a bare lead as written, rule source-list for its lead as written, rule layout for its label as written."""
    for text in (f"{lead} I can't see the image.", f"{lead} The Tuner extract (supplied text)"):
        leads = lead_starts(text)
        assert leads and leads[0][0] == 0 and leads[0][1] in ("note", "sources"), (text, leads)
        assert lead_starts(text, plain=True) == [], text
        blocks = lead_blocks(text, TUNER_GROUNDING)
        assert len(blocks) == 1 and not blocks[0].read, blocks
        assert not read_meta_paragraph(text).note and not read_source_list(text, TUNER_GROUNDING).ok and not read_layout(text).ok


@pytest.mark.parametrize("label", ["T\u0430sk:", "W\u043erking (b):", "\u0391nswer:", "\u0405olution:"])
def test_a_look_alike_label_cuts_a_block_and_is_never_read_as_layout(label):
    """Read on the skeleton, a look-alike label is a label where blocks are cut, so the text after it is a block of its own;
    rule layout reads labels as written only, so it never frees that block."""
    text = "Note: I can't see the image. " + label
    assert [k for _s, k, *_r in lead_starts(text, LAYOUT_LABEL_RE)] == ["note", "extra"]
    assert [k for _s, k, *_r in lead_starts(text, LAYOUT_LABEL_RE, plain=True)] == ["note"]
    assert not read_layout(label).ok


def test_the_skeleton_reads_every_round_4_look_alike_as_its_latin_letters():
    assert skeleton("N\u043ete: x") == "Note: x" and skeleton("\u039d.\u0392.") == "N.B." and skeleton("\u0274\u1d0f\u1d1b\u1d07") == "note"
    assert skeleton("\u1e46ote") == "Note" and skeleton("\uff2e\uff4f\uff54\uff45：") == "Note:" and skeleton("\U0001d40d\U0001d428\U0001d42d\U0001d41e") == "Note"
    assert skeleton("Notes\u0131") == "Notesi"  # a dotless i is an i: "Notesı:" is no lead (the claim channel, pinned open)
    assert skeleton("N0te") == "N0te"  # digits are never mapped: a lead is words
    assert skeleton("plain ASCII.") == "plain ASCII." and reader_text("N\u043ete") == "N\u043ete"  # the readers' own text keeps its letters
    for ch, latin in _CONFUSABLES.items():
        assert latin.isascii() and latin.isalpha() and len(latin) == 1 and not ch.isascii(), ch
        assert unicodedata.category(ch)[0] == "L", ch


@pytest.mark.parametrize("note", [n for _t, _p, n, _k in RECORDED_NOTES] + list(FURTHER_GENUINE))
def test_a_genuine_note_reads_as_before_on_the_skeleton(note):
    assert [b.read for b in lead_blocks(note, TUNER_GROUNDING)] == [True], note


# ============================================================================================ receipt and audit agree
@pytest.mark.parametrize("extra", ["N\u043ete: every quotation above holds, and not one of them is off.", "Working (fine):", "(A1) (A1) (A1) (A1)"])
def test_the_task_audit_has_no_reading_of_the_round_4_blocks_so_the_policy_decides(extra):
    """The auditor reads claims and transfers; its structural detector (``flags_self_certification``) is unchanged and shared by
    every reader. The task audit names the same findings with and without each round-4 block, and the delivery decision, the
    only reading, refuses the label (the receipt side is never laxer than the audit)."""
    _rc0, _r0, _d0, audit0 = _deliver(EN_T14)
    _rc, _r, decision, audit = _deliver(EN_T14 + "\n\n" + extra)
    assert sorted((f.code, f.severity) for f in audit.report.findings) == sorted((f.code, f.severity) for f in audit0.report.findings)
    assert _reasons(decision, NON_MATERIAL_REASON) or _reasons(decision, LEAD_REASON)


# ============================================================================================ the recorded answers
_CORE = json.loads((Path(__file__).resolve().parent / "data" / "c1_core_material.json").read_text(encoding="utf-8"))["specialists"]


def _recorded(name: str):
    item = _CORE[name]
    sup = [SuppliedText(**{k: v for k, v in s.items() if k in ("document_id", "title", "author", "text")}) for s in item.get("supplied_texts", [])]
    hub = RouterHub(signing_key=KEY, config=CFG, auditor=make_auditor())
    try:
        pid = name.replace("/", "-")
        plan = WorkPlan(plan_id="p-" + pid, request_id="r-" + pid, task_id="t-" + pid, subject=item["subject"], task_type=item["task_type"],
                        selected_agent_ids=[item["agent_id"]], allowed_document_ids=[s.document_id for s in sup])
        hub.open_task(plan)
        m, _req, rq = hub.dispatch(plan.task_id, item["agent_id"], item["question"], sup)
        assert m is not None, rq.findings
        session = DeliveryPolicy(clock=FakeClock()).start(hub, plan.task_id)
        session.install()
        _reply, rc = hub.receive(plan.task_id, m.message_id, item["response_text"], agent_id=item["agent_id"], report_id="rep-" + pid)
        return session.decide(request_message_ids=[m.message_id], receipts={rc.message_id: rc})
    finally:
        hub.close()


@pytest.mark.parametrize("name", ROUND4["recorded_counterfactual"]["refused_by_rules_6b_alone"])
def test_the_recorded_answers_the_6b_rules_alone_keep_off_the_label(monkeypatch, name):
    """The regression lens's record, pinned: with every claim counted clean these five recorded round-8 answers were FORMALLY
    CHECKED at the clearance commit and are not now, refused by rules lead-blocks and non-material-text alone (their closing
    source lines outside the knowledge bases' forms the strict reader takes, headings outside the parsers' closed label sets,
    part labels with a title, questions to the student, a limitation note with no lead). Conservative by design: each only falls
    back from the formal path, as every answer did before rule meta-note existed; recovering them without reopening condition
    6b is round 9's.

    Rewritten to the stricter rule after attack round 5 (rule ``unverified-claims``): "every claim counted clean" counted only
    the eligible material claims, so each answer's supporting claims carried no outcome, which the label no longer allows;
    every claim of each recorded answer is now counted clean (``_clean_every_claim``), and the refusal is still the 6b rules'
    alone.

    Rewritten to the stricter rule ``formal-label-withheld`` (``docs/DELIVERY.md`` condition 6d, attack round 6): the policy
    never grants FORMALLY CHECKED in the round-8 release. Where this test pinned the label it now pins that the label rule is
    the formal path's ONLY reason (every other condition holds, as before); where it pinned the reasons of a refusal it pins
    them with the label rule's reason last.

    Round-9 clearance c2b: the History pack now names hi-t14's "A war of three years and one month" (h1.12) unchecked
    (CORE-QNT-001: the paragraph dates the war's beginning, never its end; another owner's chronology fix), and the formal path
    names that unchecked working beside the 6b rules' reasons. The 6b reasons are still required of every answer; the one other
    reason allowed is that one, exactly, on hi-t14 alone (the other four answers still carry the 6b reasons and nothing else)."""
    _clean_every_claim(monkeypatch)
    decision = _recorded(name)
    assert decision.mode != "formally_checked"
    assert decision.receipt.formal.reasons[-1] == FORMAL_LABEL_REASON, decision.receipt.formal.reasons
    reasons = decision.receipt.formal.reasons[:-1]
    other = [r for r in reasons if not r.startswith((NON_MATERIAL_REASON, LEAD_REASON))]
    assert len(other) < len(reasons), decision.receipt.formal.reasons  # the 6b rules' reasons are there
    unchecked_h1_12 = ["the receipt names working that was not checked: CORE-QNT-001 (claims h1.12)"]
    assert other in (([], unchecked_h1_12) if name == "hi-t14" else ([],)), decision.receipt.formal.reasons


def test_the_recorded_answer_the_label_rule_alone_refuses(monkeypatch):
    """Rewritten to the stricter rule after attack round 5 (rule ``unverified-claims``): every claim of the recorded answer is
    counted clean (``_clean_every_claim``), not only its eligible material claims, which the label no longer allows alone.

    Rewritten to the stricter rule ``formal-label-withheld`` (``docs/DELIVERY.md`` condition 6d, attack round 6): the policy
    never grants FORMALLY CHECKED in the round-8 release. Where this test pinned the label it now pins that the label rule is
    the formal path's ONLY reason (every other condition holds, as before); where it pinned the reasons of a refusal it pins
    them with the label rule's reason last.

    Renamed after the re-review of the c1 landing (from ``test_the_recorded_answer_that_keeps_the_label``), its assertions
    unchanged: the old name stated the label, which rule ``formal-label-withheld`` (``docs/DELIVERY.md`` condition 6d)
    withholds."""
    _clean_every_claim(monkeypatch)
    assert ROUND4["recorded_counterfactual"]["formally_checked"] == ["b1/ge-2", "en-t14", "physics-fixture"]
    decision = _recorded("b1/ge-2")
    assert decision.mode == "withheld" and decision.receipt.formal.reasons == [FORMAL_LABEL_REASON], decision.receipt.formal.reasons
    assert_label_withheld_only(decision)


# ============================================================================================ linear and bounded
_TASK_8K = ("Write one analytical paragraph on how the writer uses the tuning of the piano. Keep to about 250 words. " * 80)[:8234]
HOSTILE = {
    "distinct CJK letters": ("".join(chr(0x4E00 + (i % 20000)) for i in range(300_000)), 0),
    "letters with diacritics": ("".join(chr(0xC0 + (i % 0x17F)) for i in range(300_000)), 0),
    "look-alike leads": ("N\u043ete: x. " * 40_000, 1),
    "look-alike N.B.": ("\u039d.\u0392. " * 70_000, 1),
}


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_the_skeleton_lead_reader_is_linear_on_hostile_answers(name):
    text, unread = HOSTILE[name]
    assert len(text) <= 400_000
    timing = measure(lambda: len(unread_lead_blocks(text, TUNER_GROUNDING)), bound=2.0, label=f"skeleton leads, {name}")
    assert timing.holds, timing
    assert all(r == unread for r in timing.results), (name, timing.results)


def test_the_task_wording_is_read_once_per_answer():
    """Attack round 4 measured 5.43 s for 4,000 blocks of "What the task wants: Keep to about 250 words." with an 8,234-character
    task (the wording was read again for every block). It is read once now."""
    text = "\n\n".join(["The A drifts. What the task wants: Keep to about 250 words."] * 4_000)
    units = english_units(text)
    assert "keep to about 250 words." in task_wordings(_TASK_8K)
    timing = measure(lambda: len(unread_non_material_blocks(text, units, grounding=TUNER_GROUNDING, task_wording=_TASK_8K)), bound=2.0,
                     label="layout blocks, an 8k task")
    assert timing.holds, timing
    assert all(r == 0 for r in timing.results), timing.results


@pytest.mark.parametrize("name, make", [
    ("label blocks with a long task", lambda k: "\n\n".join(["The A drifts. What the task wants: Keep to about 250 words."] * (k // 60))),
    ("look-alike leads", lambda k: "N\u043ete: x. " * (k // 9)),
    ("pure locators", lambda k: "Sources: The Tuner extract, " + "lines 3-5, " * (k // 11)),
])
def test_the_round_4_readers_grow_linearly(name, make):
    small_text, large_text = make(5_000), make(20_000)
    units = {t: english_units(t) for t in (small_text, large_text)}

    def read(text):
        unread_non_material_blocks(text, units[text], grounding=TUNER_GROUNDING, task_wording=_TASK_8K)
        unread_lead_blocks(text, TUNER_GROUNDING)
    ratio, small, large = growth(read, small_text, large_text)
    assert large < 2.0 and ratio < 8, (name, ratio, small, large)
