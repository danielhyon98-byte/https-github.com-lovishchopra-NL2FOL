"""Finding 6 of the 12 October 2026 review, second repair: a source asserts a figure only where the reader POSITIVELY
recognises an assertion.

The independent verification of the first repair found 7 of 32 non-asserting phrasings of the reviewer's case still read
as asserting n = 17, each withholding a valid counterexample (E110) and ending as INVALID_FORMALIZATION after a retry:
"Students often guess that n is 17, but this is not given.", "Claim to test: n is 17.", "In some cases n is 17.",
"Hypothesis: n is 17.", "According to rumour, n is 17.", "n = 17 ⇒ b." (U+21D2) and "b ⟺ n = 17." (U+27FA). The cause
was the reader's design: a clause counted as asserting unless it held a construction from a list of suspending ones, so
any construction the list did not know read as an assertion and uncertainty withheld the verdict.

Now (``translate.assertion``) a figure is asserted only when, besides no suspending construction governing it, the
reader positively recognises its clause as a statement: every symbol and closed-class word in it is one an assertion may
hold; a label before a colon presents what follows as given ("Given:", "Data:") or is a whole statement; and the words
before the figure's clause are recognised frame elements (connectives, subordinators that present a fact, relative
pronouns, factive frames such as "We are told that", time and place adverbials, whole clauses that end where a
recognised boundary begins). Everything else keeps the counterexample with the advisory W110/W111. The classes the
verifier named (hedges, hypotheses, reported speech, claims to test, quantified and symbolic conditionals and
biconditionals, Unicode arrows included) are pinned here phrasing by phrasing, with the asserting negative controls.
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.translate.assertion import assertion_at
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, TaskRecord, TranslationStatus as T, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider
from epinoic_logic.translate.quantities import SourceText, figures_in

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
KEY = b"positive-assertion-reader-test-key-0123"


def V(n):
    return {"op": "var", "name": n}


def I(v):
    return {"op": "int", "value": str(v)}


def eq(a, b):
    return {"op": "eq", "left": a, "right": b}


def output(problem):
    return {"problem": problem, "interpretation": {"reading": "as stated", "glossary": [], "ambiguity_flags": []}, "ambiguous": False,
            "unsupported_reason": None}


def problem(premises, conclusion, symbols):
    return {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
            "symbols": [{"name": n, "sort": s} for n, s in symbols], "premises": premises, "conclusion": conclusion}


#: The verifier's encoding (probe f6): b is DEFINED by n = 17 and the claim concludes b.
DEFINITION = problem([{"id": "D", "expr": {"op": "iff", "left": V("b"), "right": eq(V("n"), I(17))}, "label": "Define b to hold iff n equals 17.",
                       "grounding": {"kind": "task_setting"}}],
                     {"id": "C", "expr": V("b"), "label": "b necessarily holds"}, (("b", "Bool"), ("n", "Int")))
#: The verifier's E111 encoding: x = 5 is encoded and the conclusion compares x with a y no premise mentions.
FREE = problem([{"id": "P", "expr": eq(V("x"), I(5)), "label": "x equals 5", "grounding": {"kind": "task_setting"}}],
               {"id": "C", "expr": {"op": "lt", "left": V("x"), "right": V("y")}, "label": "x is less than y"}, (("x", "Int"), ("y", "Int")))


def make(claim_text, *, support=(), texts=()):
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="Mathematics", task_type="algebra")
    supporting = [ClaimRecord(**ids, claim_id=f"s{i}", claim_text=t, claim_role="evidence") for i, t in enumerate(support)]
    claim = ClaimRecord(**ids, claim_id="c", claim_text=claim_text, claim_role="quantitative", proposed_claim_kind="arithmetic",
                        supporting_claim_ids=[c.claim_id for c in supporting])
    body = " ".join([claim_text, *support])
    report = SpecialistReport(**ids, original_response=body, response_sha256=sha256_text(body), claims=[claim, *supporting],
                              supplied_texts=[SuppliedText(document_id=d, text=t) for d, t in texts], created_at="2026-10-16T00:00:00Z")
    return claim, report


def run_definition(text, where):
    """The verifier's f6 setting: the text as the task record, as a supporting claim or as a supplied text."""
    claim_text = "With b defined by n = 17, b necessarily holds."
    task = None
    if where == "task":
        claim, report = make(claim_text)
        task = TaskRecord.of("t", "r", text)
    elif where == "support":
        claim, report = make(claim_text, support=[text])
    else:
        claim, report = make(claim_text, texts=[("doc", text)])
    provider = FixtureTranslationProvider({"c": [output(DEFINITION), output(DEFINITION)]})
    outcome = verify_claim(claim, report, Translator(provider, config=CFG), config=CFG, signing_key=KEY, key_id="k", task=task)
    return outcome, provider


def codes(outcome):
    return [d.code for d in outcome.verification.diagnostics] if outcome.verification is not None else []


def reading(text, value=17):
    [f] = [f for f in figures_in(SourceText("claim", "c", text)) if f.value == value][:1]
    return assertion_at(text, f.start, f.end)


# =========================================================================== the verifier's seven phrasings

VERIFIER_SEVEN = [
    "Students often guess that n is 17, but this is not given.",
    "Claim to test: n is 17.",
    "In some cases n is 17.",
    "Hypothesis: n is 17.",
    "According to rumour, n is 17.",
    "n = 17 ⇒ b.",   # U+21D2 RIGHTWARDS DOUBLE ARROW
    "b ⟺ n = 17.",   # U+27FA LONG LEFT RIGHT DOUBLE ARROW
]


@pytest.mark.parametrize("where", ["task", "support", "doc"])
@pytest.mark.parametrize("text", VERIFIER_SEVEN)
def test_the_seven_phrasings_the_verifier_found_keep_their_counterexample(text, where):
    """Each phrasing asserts no n = 17, so the counterexample to the faithful encoding (b false, n not 17) is the verdict,
    with the advisory W110; the translator is called once (no premise requested) and nothing is withheld."""
    outcome, provider = run_definition(text, where)
    assert len(provider.calls) == 1, "no E110 rejection, so no retry asking for a premise"
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.COUNTEREXAMPLE
    assert outcome.verification.status is S.COUNTEREXAMPLE and codes(outcome) == ["W110"]
    cx = {a.symbol: a.value for a in outcome.verification.counterexample.assignments}
    assert cx["b"] == "false" and cx["n"] != "17"
    [note] = [n for n in outcome.translation.coverage if n.kind == "unasserted_definition"]
    assert not note.source_asserted and note.evidence_symbols == [] and note.source_refs == []
    assert not reading(text).asserted


# =========================================================================== every class the verifier named

NOT_ASSERTING = {
    "hedge": ["n is probably 17.", "n is likely 17.", "n seems to be 17.", "Apparently n is 17.", "n is usually 17.", "Typically, n is 17.",
              "n is supposedly 17.", "n is said to be 17.", "n might well be 17.", "Arguably n is 17.", "n, it seems, is 17.", "n is 17, it appears.",
              "n is 17, I think.", "n is 17 (unconfirmed).", "n is surely 17.", "n will be 17.", "Hopefully n is 17."],
    "hypothesis": ["Conjecture: n is 17.", "Our hypothesis is that n is 17.", "We hypothesise that n is 17.", "Assumption: n is 17.",
                   "Guess: n is 17.", "Prediction: n is 17.", "Working assumption: n = 17.", "Hypothetically, n is 17.", "n is 17 by hypothesis.",
                   "We conjecture n is 17.", "Postulate: n = 17.", "We posit that n = 17.", "Scenario: n is 17.", "Candidate: n = 17."],
    "reported speech": ["Rumour has it that n is 17.", "Rumour has it n is 17.", "Legend has it n is 17.", "Word is that n is 17.",
                        "The story goes that n is 17.", "Students guess n is 17.", "Some say n is 17.", "It is said that n is 17.",
                        "Reportedly, n is 17.", "The textbook claims n is 17.", "He told us n is 17.", "She said n is 17.",
                        "The teacher asserted that n is 17.", "Pupils report n is 17.", "News reports put n at 17.", "Historians estimated n at 17.",
                        "Many believe n is 17.", "Critics argue that n is 17.", "Smith (1990) says n is 17.", "In Smith's view, n is 17.",
                        "Students wrote that n is 17.", "Others maintain that n is 17."],
    "claim to test": ["Claim: n is 17.", "To test: n is 17.", "Test whether n is 17.", "Check: n is 17.", "Statement to evaluate: n is 17.",
                      "Is it true that n is 17?", "Prove or disprove: n is 17.", "Decide if n is 17.", "Verify that n is 17.",
                      "To be checked: n is 17.", "Our claim is that n is 17.", "True or false: n is 17.", "Show that n is 17.",
                      "Determine whether n = 17.", "Question: n = 17?", "Exercise: n = 17.", "n is 17 (to be verified).", "n = 17 remains to be tested."],
    "quantified condition": ["Sometimes n is 17.", "n is sometimes 17.", "Often n is 17.", "In many cases n is 17.", "In most cases n is 17.",
                             "For some inputs n is 17.", "There are cases where n is 17.", "n is 17 in some models.", "In certain cases n is 17.",
                             "Every time b holds, n is 17.", "Whenever b holds, n is 17.", "n is 17 whenever b holds.", "n is 17 when b holds.",
                             "Each time, n is 17.", "On average, n is 17.", "Most of the time n is 17.", "n is 17 for all inputs.",
                             "n is 17 in every case.", "As a rule, n is 17.", "Occasionally n is 17."],
    "symbolic conditional or biconditional": ["n = 17 → b.", "n = 17 ⟹ b.", "n = 17 ⟶ b.", "n = 17 => b.", "n = 17 -> b.",
                                              "n = 17 ==> b.", "b ⇐ n = 17.", "b ← n = 17.", "b ⟸ n = 17.", "b ⇔ n = 17.",
                                              "b ↔ n = 17.", "b ⟷ n = 17.", "b <=> n = 17.", "b <-> n = 17.", "b <--> n = 17.",
                                              "b ≡ (n = 17).", "(n = 17) ⊃ b.", "n = 17 ⊢ b.", "n = 17 ⊨ b.",
                                              "∀n (n = 17 → b).", "n = 17 ∨ n = 18.", "¬(n = 17).", "n = 17 ∧ b.",
                                              "b if n = 17.", "b iff n = 17.", "n := 17.", "n == 17", "n = 17 | b", "n = 17 ∴ b.",
                                              "n = 17 <- b.", "b <== n = 17.", "n = 17 --> b.", "n = 17 && b"],
}


@pytest.mark.parametrize("cls,text", [(c, t) for c, items in NOT_ASSERTING.items() for t in items])
def test_no_construction_of_the_named_classes_reads_as_an_assertion(cls, text):
    """Every phrasing of the classes the verifier named states no n = 17 (or 9 for y): the reader does not read it as
    asserted, and names the construction that decided it."""
    r = reading(text)
    assert not r.asserted, (cls, text, r)
    assert r.mood != "asserted" and (r.cue or r.mood)


@pytest.mark.parametrize("text", ["Hopefully n is 17.", "Rumour has it n is 17.", "Statement to evaluate: n is 17.", "n is 17 in some models.",
                                  "n = 17 → b.", "b ⟷ n = 17.", "Pupils opine that n is 17.", "Zorbly, n is 17.", "Blorp: n is 17."])
def test_end_to_end_each_class_keeps_the_counterexample_with_the_advisory(text):
    """End to end, one phrasing of each class (and of constructions no list names, below): W110 and the counterexample."""
    outcome, provider = run_definition(text, "task")
    assert len(provider.calls) == 1 and outcome.display_status is S.COUNTEREXAMPLE and codes(outcome) == ["W110"]


@pytest.mark.parametrize("text", ["Pupils opine that n is 17.", "Zorbly, n is 17.", "Blorp: n is 17.", "In this scenario n is 17.",
                                  "Under this reading n is 17.", "Per the brief n is 17 or so."])
def test_a_construction_the_reader_does_not_recognise_is_no_assertion(text):
    """The rule itself, not a list of suspending words: a verb, an adverbial or a label the reader does not recognise
    leaves the clause unrecognised, so it is no evidence (the default is the counterexample, never the withheld verdict)."""
    r = reading(text)
    assert not r.asserted, r


# =========================================================================== negative controls: assertions

ASSERTING = ["n is 17.", "n = 17.", "n equals 17.", "The number n equals 17.", "The value of n is 17.", "Seventeen is the value of n.",
             "We are told that n = 17.", "It is given that n = 17.", "We know that n is 17.", "We know n is 17.", "Given: n = 17.",
             "Data: n = 17.", "Facts: n is 17.", "Indeed, n is 17.", "In fact, n is 17.", "Note that n is 17.", "Recall that n = 17.",
             "Since n = 17, b holds.", "Because n = 17, b holds.", "As n is 17, b holds.", "Although n is 17, b fails.",
             "n is 17, so b holds.", "n is exactly 17.", "n is 17 and nothing else.", "Given that n = 17, b holds.",
             "Given n = 17, define b iff n = 17.", "Thus n = 17.", "Therefore n is 17.", "Answer: n = 17.", "It follows that n = 17.",
             "Clearly n is 17.", "There are 17 items.", "n is 17. Define b to hold iff n equals 17."]


@pytest.mark.parametrize("text", ASSERTING)
def test_a_recognised_statement_asserts_its_figure(text):
    r = reading(text)
    assert r.asserted, r


@pytest.mark.parametrize("text", ["n = 17.", "The number n equals 17.", "We are told that n = 17.", "Given n = 17, define b iff n = 17.",
                                  "Seventeen is the value of n.", "n is 17. Define b to hold iff n equals 17.", "It is given that n = 17.",
                                  "Given: n = 17."])
@pytest.mark.parametrize("where", ["task", "support"])
def test_a_source_that_asserts_the_figure_still_withholds_the_counterexample(text, where):
    """The pair: where the source does assert n = 17 the encoding omitted it: E110, INVALID_FORMALIZATION, fed back once
    with the asserting clause."""
    outcome, provider = run_definition(text, where)
    assert outcome.translation.status is T.INVALID_FORMALIZATION and outcome.display_status is S.INVALID_FORMALIZATION
    assert len(provider.calls) == 2
    assert any("E110" in d and "the source asserts that figure" in d for d in provider.calls[1].prior_diagnostics)


def test_a_given_before_an_instruction_is_asserted_and_the_instruction_is_not():
    """The verifier's positive control "Given n = 17, define b iff n = 17.": the given ends at its comma, so its 17 is
    asserted while the definition's 17 is not."""
    text = "Given n = 17, define b iff n = 17."
    first, second = [f for f in figures_in(SourceText("claim", "c", text)) if f.value == 17]
    assert assertion_at(text, first.start, first.end).asserted
    r = assertion_at(text, second.start, second.end)
    assert not r.asserted and r.mood in ("instruction", "definition")


# =========================================================================== E111: the free variable pair

@pytest.mark.parametrize("support,constrained", [
    ("Given x = 5, is x < y for an arbitrary integer y?", False),
    ("x = 5 and y may be any integer.", False),
    ("x = 5; y is not given.", False),
    ("x is 5. For any y, is x < y?", False),
    ("x = 5 and some guess that y is 9.", False),
    ("x = 5; y = 9 ⇒ x < y.", False),
    ("x = 5 and y = 9.", True),
    ("x is 5 and y is 9.", True),
    ("Given x = 5 and y > 7, x < y.", True),
])
def test_a_free_variable_is_constrained_only_by_a_recognised_assertion(support, constrained):
    claim, report = make("x is less than y.", support=[support])
    provider = FixtureTranslationProvider({"c": [output(FREE), output(FREE)]})
    outcome = verify_claim(claim, report, Translator(provider, config=CFG), config=CFG, signing_key=KEY, key_id="k")
    assert codes(outcome) == (["E111"] if constrained else ["W111"])
    assert outcome.display_status is (S.INVALID_FORMALIZATION if constrained else S.COUNTEREXAMPLE)
    if not constrained:
        cx = {a.symbol: a.value for a in outcome.verification.counterexample.assignments}
        assert cx["x"] == "5" and int(cx["y"]) <= 5


# =========================================================================== raising verbs and factive frames

#: Statements of fact through a raising verb or a factive frame: the writer states the figure. Found by the measurement of
#: this repair ("n turned out to be 17, so b held." read as unrecognised): recognised now, with their negative controls.
RAISED = ["n turned out to be 17, so b held.", "n turned out to be 17.", "n proved to be 17.", "n was found to be 17.", "n is known to be 17.",
          "n was shown to be 17.", "n has been shown to be 17.", "n was measured to be 17.", "The value of n turned out to be 17.",
          "So n turned out to be 17.", "In the end n turned out to be 17.", "It turned out that n was 17.", "It was found that n was 17.",
          # factive frames that sat at a line break of the frame list (each line's last and next line's first frame were
          # read as one phrase)
          "We saw that n is 17.", "We note that n is 17.", "It is established that n is 17.", "It was established that n is 17.",
          "The question gives n = 17.", "The problem states that n is 17.", "The table shows that n is 17.", "The record shows that n is 17."]
#: The same constructions that state no fact: seeming, expecting, supposing, reporting, believing, a modal, a negation,
#: a condition, a question, a quantification, a disjunction, and raising phrases the reader does not know.
NOT_RAISED = ["n seems to be 17.", "n appears to be 17.", "n is believed to be 17.", "n is said to be 17.", "n is expected to be 17.",
              "n is thought to be 17.", "n is assumed to be 17.", "n is supposed to be 17.", "n is rumoured to be 17.", "n is estimated to be 17.",
              "n is reported to be 17.", "n is likely to be 17.", "n is unlikely to be 17.", "n is claimed to be 17.", "n is alleged to be 17.",
              "n is presumed to be 17.", "n is predicted to be 17.", "n is considered to be 17.", "n is deemed to be 17.", "n is held to be 17.",
              "n is taken to be 17.", "n is meant to be 17.", "n is going to be 17.", "n is bound to be 17.", "n is certain to be 17.",
              "n turned out not to be 17.", "n is known not to be 17.", "If n turned out to be 17, b would hold.", "n may turn out to be 17.",
              "n will turn out to be 17.", "Does n turn out to be 17?", "Whether n turned out to be 17 is unclear.", "Suppose n turned out to be 17.",
              "n was found to be 17 in some cases.", "n turned out to be 17 or 18.", "n turned to be 17."]


@pytest.mark.parametrize("text", RAISED)
def test_a_raising_verb_of_fact_or_a_factive_frame_states_the_figure(text):
    r = reading(text)
    assert r.asserted, r


@pytest.mark.parametrize("text", NOT_RAISED)
def test_seeming_reporting_supposing_or_an_unknown_raising_phrase_states_no_figure(text):
    r = reading(text)
    assert not r.asserted, r


@pytest.mark.parametrize("text,asserted", [("n turned out to be 17, so b held.", True), ("n seems to be 17, so b holds.", False),
                                           ("n is believed to be 17, so b holds.", False)])
def test_end_to_end_a_raised_statement_is_evidence_and_a_seeming_one_is_not(text, asserted):
    """The pair through the pipeline: the statement withholds the counterexample (E110, fed back once with the asserting
    clause); the seeming keeps it with the advisory W110 and one provider call."""
    outcome, provider = run_definition(text, "support")
    if asserted:
        assert outcome.display_status is S.INVALID_FORMALIZATION and len(provider.calls) == 2
        assert any("E110" in d for d in provider.calls[1].prior_diagnostics)
    else:
        assert outcome.display_status is S.COUNTEREXAMPLE and codes(outcome) == ["W110"] and len(provider.calls) == 1


def test_reading_values_other_than_seventeen():
    """The reader reads a figure, not the number 17: the same constructions around 9 behave the same."""
    assert reading("y = 9.", 9).asserted and not reading("y = 9 ⇒ b.", 9).asserted
    assert not reading("Hypothesis: y is 9.", 9).asserted and reading("Given: y is 9.", 9).asserted
    assert reading("The rate fell from $4.03 to $2.80.", Fraction("4.03")).asserted


def test_the_translation_prompt_names_the_constructions_that_assert_nothing():
    from epinoic_logic.translate import prompts
    text = prompts.load_prompt(prompts.TRANSLATE_PROMPT_VERSION)
    for needle in ('"in some cases"', '"probably"', '"Hypothesis:"', '"Claim to test:"', '"according to rumour"', "n = 17 \u21d2 b",
                   "b \u27fa n = 17", "never as a premise"):
        assert needle in text, needle
