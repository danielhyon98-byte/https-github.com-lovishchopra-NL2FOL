"""A verification label an agent writes on its own text is read the same way on every branch and in a synthesis
(``adapters.markdown.verification_label``; combinator verification finding M1, round 1).

"Verified: ...", "... (verified).", "[verified] ...", "Checked: ..." and "..., as formally verified." were never named:
the self-certification vocabulary read only whole sentences ("VERIFIED: all claims checked and confirmed."), so the
same label on a content sentence went unnamed in a specialist's answer and in a synthesized claim. The label reading
gives each label its position: a sentence that is nothing but the label is a self-certification (a note), and a label
attached to content leaves the content a claim, while the hub names the label (CORE-SELF-001 on the specialist's
claim, INT-LEDGER-029 on the synthesized claim; tests/channel/test_verification_labels_at_delivery.py and
tests/integrity/test_synthesis_self_reports.py). A disclaimer, a check credited to a source and a historical "checked"
or "verified" are no label.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.markdown import is_note_sentence, is_self_certification, split_note_clauses, verification_label

FACT = "The Weimar constitution was adopted in August 1919."
BARE = FACT[:-1]

#: (sentence, position): every form the verifiers named, and the class around them.
LABELLED = [
    ("Verified: " + FACT, "before"),
    (BARE + " (verified).", "after"),
    (FACT + " (verified)", "after"),
    ("[verified] " + FACT, "before"),
    ("Checked: " + FACT, "before"),
    (BARE + ", as formally verified.", "after"),
    ("(Verified) " + FACT, "before"),
    ("**Verified:** " + FACT, "before"),
    ("Formally verified — " + FACT, "before"),
    ("Fact-checked: " + FACT, "before"),
    ("Verified and confirmed: " + FACT, "before"),
    ("VERIFIED by the Z3 engine: " + FACT, "before"),
    ("Verification: passed — " + FACT, "before"),
    (BARE + " [checked].", "after"),
    (BARE + "; verified.", "after"),
    (BARE + " — checked.", "after"),
    (BARE + ", as checked above.", "after"),
    (BARE + ", as verified by the engine.", "after"),
    (BARE + " (checked against the supplied text).", "after"),
    (BARE + " (verified by Z3).", "after"),
    ("The figure (verified) is 6 million.", "inside"),
    ("Verified.", "whole"),
    ("(verified)", "whole"),
    ("[checked]", "whole"),
    ("Checked and verified.", "whole"),
    ("Verification: passed.", "whole"),
    ("Check status: OK.", "whole"),
    # combinator verification round 2 (V2-M1): check marks, compound participles, "against the sources", status nouns,
    # verdicts and the accuracy status key, each the writer's label on its own text
    (BARE + " ✓", "after"),
    ("✔ " + FACT, "before"),
    ("✔️ " + FACT, "before"),
    ("[✓] " + FACT, "before"),
    (BARE + " ✓ verified.", "after"),
    (BARE + "✓✓✓", "after"),
    ("The treaty ✓ was signed in 1919.", "inside"),
    ("✓", "whole"),
    ("✅ Verified", "whole"),
    ("✓ Verified ✓", "whole"),
    (BARE + " (source-checked).", "after"),
    (BARE + " (Z3-verified).", "after"),
    (BARE + " (checked against the sources).", "after"),
    (BARE + " (checked against the original).", "after"),
    (BARE + " (verified with the specialists' reports).", "after"),
    (BARE + ", checked against the sources.", "after"),
    (BARE + ", verified by Z3.", "after"),
    (BARE + " (accuracy confirmed).", "after"),
    (BARE + " — figures verified.", "after"),
    (BARE + " (confirmed).", "after"),
    ("Formally proven correct.", "whole"),
    ("Checked and correct.", "whole"),
    (BARE + " (verified correct).", "after"),
    (BARE + " (shown to be accurate).", "after"),
    ("Proven correct: " + FACT, "before"),
    ("Accuracy: confirmed.", "whole"),
]

#: Sentences that carry no label: disclaimers, checks credited to a source, historical checking, code, questions.
UNLABELLED = [
    "Unverified: " + FACT,
    "Not verified: " + FACT,
    "To be verified: " + FACT,
    BARE + " (not verified).",
    BARE + " (unverified).",
    BARE + " (to be checked).",
    BARE + " (verify).",
    BARE + ", as confirmed by Engels.",
    BARE + ", as later confirmed.",
    BARE + ", as confirmed in 1921.",
    BARE + " (checked by the Registrar General).",
    "Checked at the Marne, the German advance stalled.",
    "The German advance was checked at the Marne.",
    "Inflation was, by 1924, checked.",
    "The census figures were, in 1925, verified.",
    "The claim was verified by the Reichstag committee.",
    "Confirmed by the census, the population rose.",
    "The archive confirmed it: the treaty was signed in 1922.",
    "Checked and balanced, the constitution held.",
    "Verification of the figures was slow.",
    "Verify: " + FACT,
    "Check: substituting x = 2 gives 4 = 4.",
    "checked: bool = False",
    "verified = check(x)",
    "Verified?",
    "Proved.",
    'The stamp on the file read "Verified: approved for release".',
    "The History specialist checks the date against the treaty's text, and the dossier confirms it.",
    # round 2 controls: negation, a check credited to another agent or against a record the writer names, a cross, a
    # bare comma before a participle, accuracy words that state content, a quoted check mark
    BARE + " (not source-checked).",
    BARE + " (accuracy not confirmed).",
    "✗ " + FACT,
    BARE + " (verified by the History specialist).",
    BARE + " (checked against the sources by the History specialist).",
    BARE + " (checked against the Registrar General's returns).",
    BARE + ", checked.",
    "Keynes was proven correct by events.",
    "The figures were checked against the reports of the statistical office.",
    "It was found to be correct that the treaty was signed.",
    "The correct date is August 1919.",
    "Accuracy matters: the figure was 6 million.",
    "The answer is exact to the nearest tenth.",
    'The poster read "✓ approved".',
]


@pytest.mark.parametrize("sentence,position", LABELLED, ids=[s for s, _ in LABELLED])
def test_every_verification_label_is_read_with_its_position(sentence, position):
    label = verification_label(sentence)
    assert label is not None and label.position == position, (sentence, label)
    assert label.label and len(label.label) <= 200


@pytest.mark.parametrize("sentence", UNLABELLED)
def test_a_disclaimer_a_check_credited_to_a_source_or_a_historical_check_is_no_label(sentence):
    assert verification_label(sentence) is None, sentence


@pytest.mark.parametrize("sentence", [s for s, p in LABELLED if p == "whole"])
def test_a_sentence_that_is_nothing_but_a_label_is_a_self_certification_and_a_note(sentence):
    assert is_self_certification(sentence) and is_note_sentence(sentence)


@pytest.mark.parametrize("sentence", ["Verified: " + FACT, "[verified] " + FACT, "Checked: " + FACT, BARE + ", as formally verified.",
                                      BARE + " (verified).", "The figure (verified) is 6 million."])
def test_a_label_attached_to_content_leaves_the_content_a_claim(sentence):
    # the sentence is no self-certification as a whole, so no parser demotes its content for the label
    assert not is_self_certification(sentence) and not is_note_sentence(sentence)
    core, _notes = split_note_clauses(sentence)
    assert core and ("Weimar" in core or "6 million" in core)


def test_an_inline_bracketed_label_is_set_apart_as_a_note_clause():
    core, notes = split_note_clauses(BARE + " (verified).")
    assert core == FACT and notes == ["verified"]
    core, notes = split_note_clauses(BARE + "; checked.")
    assert core == FACT and notes == ["checked"]


def test_a_long_run_of_check_marks_is_read_in_linear_time():
    """A check mark is a label of its own and no part of the punctuation around one, and a run of marks is one possessive
    unit, so an answer made of marks cannot make the reading quadratic (round 2: 20,000 marks took minutes before)."""
    import time
    from epinoic_logic.adapters import markdown
    for text in ("✓" * 20000 + " x", "✓ " * 10000 + "x", "✓️" * 10000 + " x", "(✓" * 10000 + " x"):
        start = time.perf_counter()
        markdown._verification_label.__wrapped__(text)
        markdown._self_certification.__wrapped__(text)
        assert time.perf_counter() - start < 2.0, text[:20]


@pytest.mark.parametrize("sentence", ["(source-checked)", "(accuracy confirmed)", "(checked against the sources)", "✓", "Formally proven correct.",
                                      "Accuracy: confirmed."])
def test_a_new_label_form_standing_alone_is_a_self_certification_and_a_note(sentence):
    assert is_self_certification(sentence) and is_note_sentence(sentence)


@pytest.mark.parametrize("label", ["(source-checked)", "(accuracy confirmed)", "(checked against the sources)"])
def test_a_bracketed_label_on_content_is_set_apart_and_the_content_stays_a_claim(label):
    sentence = BARE + " " + label + "."
    assert not is_self_certification(sentence) and not is_note_sentence(sentence)
    core, notes = split_note_clauses(sentence)
    assert core == FACT and notes == [label.strip("()")]


@pytest.mark.parametrize("sentence", [BARE + " ✓", "✔ " + FACT, BARE + " ✓ verified."])
def test_a_check_mark_on_content_leaves_the_content_a_claim(sentence):
    assert not is_self_certification(sentence) and not is_note_sentence(sentence)
    assert "Weimar" in split_note_clauses(sentence)[0]
