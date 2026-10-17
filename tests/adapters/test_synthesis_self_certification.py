"""Where the combinator is the writer, its own product is the answer itself (combinator verification round 2, V2-M1).

The hub reads a synthesis with ``adapters.markdown.is_synthesis_self_certification``: every self-certification a
specialist's answer is read for (``is_self_certification``), and the combined answer named as the thing certified ("The
synthesis has been verified.", "This synthesis is correct.", "Every synthesized claim was checked against the sources.").
Before, the hub read a synthesis with the specialists' rules only, whose answer is "this answer" or "this paragraph", so
none of these was named. On a specialist's branch the same words are content ("the synthesis of ammonia", "This synthesis
was confirmed by NMR"), so the specialists' reading keeps them out: a false self-certification there would take content
out of the checks.

The writer's own hedges give the certainty the History and generic parsers record (``adapters.markdown.hedged_certainty``;
round 2, V2-L1): before, "probably" (History) and "may have" (generic) were recorded as established, so INT-LEDGER-003
had nothing to hold a stronger synthesis against.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
from epinoic_logic.adapters.markdown import hedged_certainty, is_self_certification, is_synthesis_self_certification
from epinoic_logic.branches.generic_parser import GenericTextParser

SELF_REPORTS = [
    "The synthesis has been verified.",
    "This synthesis is correct.",
    "The combined answer is accurate.",
    "The whole synthesis above has been checked.",
    "Every synthesized claim was checked against the sources.",
    "All claims in this synthesis were verified.",
    "The synthesized claims have been cross-checked.",
    "The synthesis is faithful to the sources.",
    "This synthesis is correct in every detail.",
    "The synthesis accurately reflects the sources.",
    "The combined answer matches the specialists' reports.",
    "The synthesis is consistent with every source claim.",
    "This synthesis has passed every check.",
    "Z3 has verified this synthesis.",
    "The hub accepted the synthesis.",
    "Nothing in this synthesis needs checking.",
    "The synthesis needs no further checking.",
    "Formally proven correct.",
    "VERIFIED: all claims checked and confirmed.",
]

NOT_SELF_REPORTS = [
    "The synthesis has not been verified.",
    "This synthesis should be checked against the sources.",
    "The synthesis may not be accurate.",
    "The synthesis was checked by the History specialist.",
    "The synthesis was confirmed by NMR spectroscopy.",
    "The synthesis of ammonia was confirmed in 1909.",
    "The synthesis of ammonia is exothermic.",
    "The synthesis reports the History specialist's view that the treaty was harsh.",
    'The poster read "this synthesis is correct".',
    "The combined answer gives two dates for the treaty.",
    "Protein synthesis is accurate because ribosomes proofread.",
]


@pytest.mark.parametrize("sentence", SELF_REPORTS)
def test_the_combined_answer_certifying_its_own_checking_is_a_self_report_in_a_synthesis(sentence):
    assert is_synthesis_self_certification(sentence), sentence


@pytest.mark.parametrize("sentence", NOT_SELF_REPORTS)
def test_negation_a_modal_another_agent_a_quotation_or_another_synthesis_is_no_self_report(sentence):
    assert not is_synthesis_self_certification(sentence), sentence


@pytest.mark.parametrize("sentence", ["The synthesis has been verified.", "This synthesis is correct.", "The synthesis was confirmed.",
                                      "The combined answer is accurate."])
def test_the_specialists_reading_does_not_read_a_synthesis_as_the_writers_answer(sentence):
    """A chemistry or biology answer says "the synthesis" of its content: the specialists' reading leaves it a claim."""
    assert not is_self_certification(sentence), sentence


@pytest.mark.parametrize("sentence,certainty", [
    ("Article 48 probably allowed the president to rule by decree in emergencies.", "probable"),
    ("The Wall Street Crash of October 1929 may have ended the American loans.", "possible"),
    ("The crash might have hastened the end of the loans.", "possible"),
    ("The crash could have hastened the end of the loans.", "possible"),
    ("Possibly the crash hastened the end of the loans.", "possible"),
    ("Perhaps the crash hastened the end of the loans.", "possible"),
    ("Demand may be inelastic in the short run.", "possible"),
    ("The fall was most likely caused by the banking crisis.", "probable"),
    ("In all likelihood the fall began in 1929.", "probable"),
    ("It is likely that the fall began in 1929.", "probable"),
    ("The crash is likely to have hastened the end of the loans.", "probable"),
    ("Presumably the crash hastened the end of the loans.", "probable"),
    ("This suggests insufficient adjustment.", "probable"),
    ("The blockade appears to have forced the withdrawal.", "probable"),
])
def test_the_writers_hedge_gives_the_certainty(sentence, certainty):
    assert hedged_certainty(sentence) == certainty


@pytest.mark.parametrize("sentence", [
    "The Weimar constitution was adopted in August 1919.",
    "The blockade made withdrawal likely.",
    "The model lines show a likely allocation.",
    "It was an unlikely alliance.",
    "A provisional government took power in November 1918.",
    "Prices could be raised to cover the tax.",
    'The narrator\'s closing observation that "we all could have been to blame" spreads culpability.',
    'The priest\'s reply, "Perhaps before God", defers the judgement.',
])
def test_content_a_quotation_or_an_option_is_no_hedge(sentence):
    assert hedged_certainty(sentence) is None


def _parse(parser, text: str, subject: str, agent: str):
    return {c.claim_text: c.certainty for c in parser.parse_response(text, request_id="req-c", task_id="task-c", report_id="rep-c", subject=subject,
                                                                       task_type="short_answer", agent_id=agent).claims}


def test_the_history_parser_records_probably_and_possibly_with_their_certainty():
    got = _parse(HistorySpecialistAdapter(), "Article 48 probably allowed the president to rule by decree in emergencies. "
                 "The Reichstag possibly lost its majority in 1930 because of the crisis. The Weimar constitution was adopted in August 1919.",
                 "History", "history-specialist")
    assert got["Article 48 probably allowed the president to rule by decree in emergencies."] == "probable"
    assert got["The Reichstag possibly lost its majority in 1930 because of the crisis."] == "possible"
    assert got["The Weimar constitution was adopted in August 1919."] == "established"


def test_the_generic_parser_records_may_have_and_probably_with_their_certainty():
    got = _parse(GenericTextParser(), "Unemployment reached about 6 million in 1932. The Wall Street Crash of October 1929 may have ended the American "
                 "loans to a limited extent. Firms probably cut investment first.", "Economics", "economics-specialist")
    assert got["Unemployment reached about 6 million in 1932."] == "established"
    assert got["The Wall Street Crash of October 1929 may have ended the American loans to a limited extent."] == "possible"
    assert got["Firms probably cut investment first."] == "probable"


def test_a_parser_never_raises_a_certainty_it_already_lowered():
    """The History parser keeps the weaker of its own cue reading and the shared hedge reading."""
    got = _parse(HistorySpecialistAdapter(), "Some historians argue that the treaty probably weakened the republic in 1919.", "History", "history-specialist")
    assert set(got.values()) == {"possible"}
