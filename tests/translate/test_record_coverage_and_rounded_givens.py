"""Findings 6 and 1/9 of the 12 October 2026 review, third repair: what a supplied text or the task record asserts is
evidence of an omission, a lower-case symbol opens a sentence of its own, and a rounded given grounds at its stated
tolerance.

The third independent verification found:

* E111 read its evidence only from the claim and its supporting claims, although the pipeline's own account says the
  supplied texts and the task record are consulted too. "Here x = 5 and y = 9." withheld the counterexample to an
  encoding that omits y = 9 when it was a supporting claim (E111), but showed that counterexample as the verdict
  (COUNTEREXAMPLE, advisory W111) when the same sentence was a supplied text or the task record, the most
  authoritative sources. The coverage assessment now reads every source. A figure of a supplied text or of the task is
  evidence only in a clause about the symbol (it names it, counts what describes it, or shares the words that describe
  it); the answer's own figures link as before.
* A sentence that starts with a lower-case variable was not split from the sentence before it, so the instruction that
  opened that sentence governed it too: "Define b to hold iff n equals 17. n = 17." and "Define b. n = 17." read the
  second 17 as part of the instruction (W110 and the counterexample, where the source asserts n = 17). A full stop before
  a lower-case symbol that opens a statement now ends the sentence; a lower-case word that continues the sentence
  ("then", a word after an abbreviation) does not. In the same class, a question opened by a clause that presents a
  fact ("Given x = 5 and y = 9, is x < y?") no longer governs that clause: the given is asserted, and the question
  governs what follows it.
* A new regression of the precision repair: the exact transcription x = 0.33 of the supplied fact "x is 0.33 to 2
  decimal places." failed grounding, because "0.33 to 2" was read as one end of a range, and the stated-tolerance
  interval [0.325, 0.335), which the precision step demands when the rounding matters, always failed the excerpt check,
  so no faithful encoding of a rounded given could ground. The numeral of a precision cue is no end of a range now, and a
  figure stated as rounded establishes the ends of the interval it states (one recorded derivation), never a wider or
  narrower interval; an exact or given figure states no interval at all.

Every case is paired with negative controls: phrasings that assert nothing keep the counterexample with the advisory, a
record figure about something else is no evidence, and intervals that are not the stated tolerance stay unestablished.
"""
from __future__ import annotations

import json
from fractions import Fraction

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.assertion import assertion_at, stated_as
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, TaskRecord, TranslationStatus as T, sha256_text
from epinoic_logic.translate.coverage import assess_unconstrained
from epinoic_logic.translate.grounding import check_problem_grounding
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.quantities import SourceText, _sentences, figures_in, in_precision_cue, stated_intervals
from epinoic_logic.translate.review import SemanticReviewer

from ..timing import measure

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
KEY = b"record-coverage-and-rounded-givens-key-01"
FAITHFUL = {"verdict": "faithful", "issues": []}


def V(n):
    return {"op": "var", "name": n}


def I(v):
    return {"op": "int", "value": str(v)}


def R(v):
    return {"op": "real", "value": str(v)}


def eq(a, b):
    return {"op": "eq", "left": a, "right": b}


def cmp(op, a, b):
    return {"op": op, "left": a, "right": b}


def between(lo, hi, lo_op="ge", hi_op="lt"):
    return {"op": "and", "args": [cmp(lo_op, V("x"), R(lo)), cmp(hi_op, V("x"), R(hi))]}


def output(problem):
    return {"problem": problem, "interpretation": {"reading": "as stated", "glossary": [], "ambiguity_flags": []}, "ambiguous": False,
            "unsupported_reason": None}


def problem(premises, conclusion, symbols):
    return {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
            "symbols": [{"name": n, "sort": s, **({"meaning": m} if m else {})} for n, s, m in symbols], "premises": premises,
            "conclusion": conclusion}


def make(claim_text, *, support=(), texts=()):
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="Mathematics", task_type="algebra")
    supporting = [ClaimRecord(**ids, claim_id=f"s{i}", claim_text=t, claim_role="evidence") for i, t in enumerate(support)]
    claim = ClaimRecord(**ids, claim_id="c", claim_text=claim_text, claim_role="quantitative", proposed_claim_kind="arithmetic",
                        supporting_claim_ids=[c.claim_id for c in supporting])
    body = " ".join([claim_text, *support])
    report = SpecialistReport(**ids, original_response=body, response_sha256=sha256_text(body), claims=[claim, *supporting],
                              supplied_texts=[SuppliedText(document_id=d, text=t) for d, t in texts], created_at="2026-10-16T00:00:00Z")
    return claim, report


def run(claim_text, responses, *, where=None, record=None, review=None):
    """Translate and verify ``claim_text`` with ``record`` as a supporting claim ('support'), a supplied text ('text') or
    the task record ('task')."""
    claim, report = make(claim_text, support=[record] if where == "support" else (), texts=[("doc", record)] if where == "text" else ())
    task = TaskRecord.of("t", "r", record) if where == "task" else None
    provider = FixtureTranslationProvider({"c": responses})
    reviewer = SemanticReviewer(FixtureReviewProvider({"c": review})) if review is not None else None
    outcome = verify_claim(claim, report, Translator(provider, config=CFG), reviewer, config=CFG, signing_key=KEY, key_id="k", task=task)
    return outcome, provider


def codes(outcome):
    return [d.code for d in outcome.verification.diagnostics] if outcome.verification is not None else []


def counterexample(outcome):
    return {a.symbol: a.value for a in outcome.verification.counterexample.assignments}


def reading(text, value, k=0):
    figures = [f for f in figures_in(SourceText("claim", "c", text)) if f.value == value]
    f = figures[k]
    return assertion_at(text, f.start, f.end)


# =========================================================================== E111: every source is read

#: The verifier's E111 encoding: x = 5 is encoded and the conclusion compares x with a y no premise mentions.
FREE = problem([{"id": "P", "expr": eq(V("x"), I(5)), "label": "x equals 5", "grounding": {"kind": "task_setting"}}],
               {"id": "C", "expr": cmp("lt", V("x"), V("y")), "label": "x is less than y"}, (("x", "Int", None), ("y", "Int", None)))

#: Sources that assert y = 9 (or a bound on y) about y: the encoding omitted what they state.
ASSERTED_RECORDS = ["Here x = 5 and y = 9.", "x = 5 and y = 9.", "We are told that x = 5 and y = 9.", "Given: x = 5, y > 7.",
                    "Given x = 5 and y = 9, is x < y?"]
WHERE = ["support", "text", "task"]
_LOCATOR_KIND = {"support": "supporting_claim", "text": "supplied_text", "task": "task"}


@pytest.mark.parametrize("where", WHERE)
@pytest.mark.parametrize("record", ASSERTED_RECORDS)
def test_a_free_symbol_whose_figure_any_source_asserts_is_no_verdict(record, where):
    """The verifier's violation and its class: a figure the claim's supporting claim, a supplied text or the task record
    asserts about y, and the encoding omits, withholds the counterexample (E111, displayed INVALID_FORMALIZATION) wherever
    it is stated; the evidence names the asserting clause of that source, and the engine's signed result carries the same
    decision. Before the repair the supplied text and the task record gave COUNTEREXAMPLE with W111."""
    outcome, provider = run("x is less than y.", [output(FREE), output(FREE)], where=where, record=record)
    assert len(provider.calls) == 1
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.INVALID_FORMALIZATION
    assert outcome.verification.status is S.COUNTEREXAMPLE and codes(outcome) == ["E111"]
    [note] = [n for n in outcome.translation.coverage if n.kind == "unconstrained_symbol"]
    assert note.source_asserted and note.evidence_symbols == ["y"] and note.evidence
    assert {(r.locator or "").split(" ")[0] for r in note.source_refs} == {_LOCATOR_KIND[where]}
    y = next(s for s in outcome.translation.problem.symbols if s.name == "y")
    assert y.grounding is not None and y.grounding.verified is True
    assert not outcome.release.permitted


#: Sources that mention y = 9 without asserting it, or that leave y open: the counterexample is the verdict on the encoding.
NOT_ASSERTED_RECORDS = ["Given x = 5, is x < y for an arbitrary integer y?", "x = 5, and y could be 9.", "If y = 9, then x < y.",
                        "Is y equal to 9?", "x = 5 and y is not 9.", "Some say y is 9.", "Hypothesis: y is 9.", "x = 5; y = 9 ⇒ x < y.",
                        "If x = 5 and y = 9, is x < y?", "Given that y could be 9, is x < y?"]


@pytest.mark.parametrize("where", WHERE)
@pytest.mark.parametrize("record", NOT_ASSERTED_RECORDS)
def test_a_source_that_does_not_assert_the_figure_keeps_the_counterexample(record, where):
    """The negative half of the pair, in every source: the reviewer's own question (y arbitrary), a possibility, a
    condition, a question, a negation, reported speech, a hypothesis and a symbolic implication assert no y = 9, and a
    question opened by a condition or a hedged given governs its whole sentence. The counterexample (x = 5, y not above 5)
    stands with the advisory W111."""
    outcome, provider = run("x is less than y.", [output(FREE), output(FREE)], where=where, record=record)
    assert len(provider.calls) == 1
    assert outcome.display_status is S.COUNTEREXAMPLE and codes(outcome) == ["W111"]
    cx = counterexample(outcome)
    assert cx["x"] == "5" and int(cx["y"]) <= 5
    [note] = [n for n in outcome.translation.coverage if n.kind == "unconstrained_symbol"]
    assert not note.source_asserted and note.evidence_symbols == [] and note.source_refs == []


#: An encoding whose symbols nothing describes and that no source names: the claim compares "the first number" with
#: "the second".
UNNAMED = problem([{"id": "P", "expr": eq(V("x"), I(5)), "label": "the first number is 5", "grounding": {"kind": "task_setting"}}],
                  {"id": "C", "expr": cmp("lt", V("x"), V("y")), "label": "the first number is less than the second"},
                  (("x", "Int", None), ("y", "Int", None)))


@pytest.mark.parametrize("where", ["text", "task"])
@pytest.mark.parametrize("record", ["The table lists 9 rows.", "The answer has 9 parts.", "The total was 9."])
def test_a_record_figure_is_evidence_only_in_a_clause_about_the_symbol(record, where):
    """A supplied text or the task record is read strictly: a figure there is evidence about y only when its clause names
    y, counts what describes y, or shares the words that describe y. Here nothing describes y and no source names it, so
    no record figure is about it, whatever value it has: the counterexample stands (W111)."""
    outcome, _ = run("The first number is less than the second.", [output(UNNAMED), output(UNNAMED)], where=where, record=record)
    assert outcome.display_status is S.COUNTEREXAMPLE and codes(outcome) == ["W111"]
    [note] = [n for n in outcome.translation.coverage if n.kind == "unconstrained_symbol"]
    assert not note.source_asserted and "not about y" in note.detail


@pytest.mark.parametrize("where", ["text", "task"])
def test_a_record_figure_that_counts_what_the_symbol_describes_is_evidence(where):
    """The positive control of the strict reading: y's meaning describes pupils, and the record states "The class has 9
    pupils.": a figure that counts what describes y is about y, so the omission withholds the counterexample (E111). A
    figure that counts something else ("12 desks") is not about y (W111)."""
    described = json.loads(json.dumps(FREE))
    described["symbols"][1]["meaning"] = "the number of pupils in the class"
    outcome, _ = run("x is less than y.", [output(described), output(described)], where=where, record="Here x = 5. The class has 9 pupils.")
    assert outcome.display_status is S.INVALID_FORMALIZATION and codes(outcome) == ["E111"]
    outcome, _ = run("x is less than y.", [output(described), output(described)], where=where, record="Here x = 5. The class has 12 desks.")
    assert outcome.display_status is S.COUNTEREXAMPLE and codes(outcome) == ["W111"]


def test_reading_every_figure_of_a_long_record_for_an_unencoded_reason_stays_linear():
    """E111 now reads every figure of the supplied texts and the task record, which are untrusted and long: 100,000
    characters of figures, none asserted about y, are read under 2 s (measured as in tests/timing.py), and every figure is
    passed over with its reason."""
    unit = "In 1960 the table listed 9 rows, if y could be 9, and 12 columns; y is not 3. "
    text = (unit * (100_000 // len(unit) + 1))[:100_000]
    prob = Problem.model_validate(FREE)
    sources = [SourceText("claim", "c", "x is less than y."), SourceText("supplied_text", "long", text)]
    timing = measure(lambda: assess_unconstrained(prob, sources), bound=2.0, label="assess_unconstrained")
    assert timing.holds, timing
    note = timing.results[0]
    assert note is not None and not note.source_asserted and note.evidence == []


# =========================================================================== a lower-case symbol opens a sentence

#: (text, the occurrence of 17 read): the second sentence opens with a lower-case symbol and asserts the figure.
LOWER_CASE_STARTS = [
    ("Define b to hold iff n equals 17. n = 17.", 1),   # the verifier's case
    ("Define b. n = 17.", 0),                           # the verifier's case: a one-letter word before the full stop
    ("Define b to hold iff n equals 17. n is 17.", 1),
    ("Define b to hold iff n equals 17. n equals 17.", 1),
    ("Is b true? n = 17.", 0),
    ("Suppose b holds. n = 17.", 0),
    ("Define b. x1 = 17.", 0),
    ("Define b. num_states = 17.", 0),
    ("Define b. θ = 17.", 0),
    ("Define b. speed = 17.", 0),
    ("Define b. a = 17.", 0),
]


@pytest.mark.parametrize("text,k", LOWER_CASE_STARTS)
def test_a_sentence_that_opens_with_a_lower_case_symbol_is_a_sentence_of_its_own(text, k):
    """A full stop before a lower-case symbol that opens a statement (a single letter, an identifier with a digit or an
    underscore, a Greek letter, a word a comparison sign follows) ends the sentence, as a full stop before a capital does:
    the instruction, supposition or question of the sentence before governs nothing after it."""
    r = reading(text, 17, k)
    assert r.asserted, r
    assert len(_sentences(text)) == 2


#: A lower-case word that continues the sentence: the construction that opened the sentence still governs the figure.
CONTINUED = [
    ("Suppose b holds. then n = 17.", "supposition"),         # "then" continues the supposition
    ("Define b, i.e. n = 17.", "instruction"),                 # the full stop closes an abbreviation
    ("Define b. a total of 17 was given.", "instruction"),     # the article "a" before a word, no comparison: no symbol
    ("Define b. approximately 17 were given.", "instruction"), # a lower-case word that is no symbol
]


@pytest.mark.parametrize("text,mood", CONTINUED)
def test_a_lower_case_word_that_is_no_symbol_continues_the_sentence(text, mood):
    r = reading(text, 17)
    assert not r.asserted and r.mood == mood, r
    assert len(_sentences(text)) == 1


def test_the_sentence_spans():
    def spans(text):
        return [text[a:b] for a, b in _sentences(text)]
    assert spans("Define b. n = 17.") == ["Define b.", " n = 17."]
    assert spans("x is 0.5. y is 0.25.") == ["x is 0.5.", " y is 0.25."]
    assert spans("Suppose b holds. then n = 17.") == ["Suppose b holds. then n = 17."]
    assert spans("Define b, i.e. n = 17.") == ["Define b, i.e. n = 17."]
    assert spans("Define b. i.e. n = 17.") == ["Define b. i.e. n = 17."]  # the 'i' of 'i.e.' is no symbol
    assert spans("Define b. e.g. n = 17.") == ["Define b. e.g. n = 17."]
    assert spans("We met at 5 p.m. the next day.") == ["We met at 5 p.m. the next day."]
    assert spans("The value is 0.5. n = 2.") == ["The value is 0.5.", " n = 2."]
    assert spans("Growth was 2.5 per cent. It rose.") == ["Growth was 2.5 per cent.", " It rose."]  # unchanged before a capital


#: The verifier's E110 encoding: b is DEFINED by n = 17 and the claim concludes b.
DEFINITION = problem([{"id": "D", "expr": {"op": "iff", "left": V("b"), "right": eq(V("n"), I(17))}, "label": "Define b to hold iff n equals 17.",
                       "grounding": {"kind": "task_setting"}}],
                     {"id": "C", "expr": V("b"), "label": "b holds"}, (("b", "Bool", None), ("n", "Int", None)))
DEFINITION_CLAIM = "b holds, by the definition that compares n with 17."


@pytest.mark.parametrize("where", WHERE)
@pytest.mark.parametrize("record", ["Define b to hold iff n equals 17. n = 17.", "Define b. n = 17.", "Given n = 17, does b hold?"])
def test_a_figure_asserted_after_an_instruction_or_before_a_question_is_no_verdict(record, where):
    """End to end in every source: the asserted n = 17 that the encoding only defines withholds the counterexample (E110,
    INVALID_FORMALIZATION), fed back once with the asserting clause, never with a request to add what would make the claim
    follow."""
    outcome, provider = run(DEFINITION_CLAIM, [output(DEFINITION), output(DEFINITION)], where=where, record=record)
    assert outcome.translation.status is T.INVALID_FORMALIZATION and outcome.display_status is S.INVALID_FORMALIZATION
    assert len(provider.calls) == 2
    feedback = "\n".join(provider.calls[1].prior_diagnostics)
    assert "E110" in feedback and "the source asserts that figure" in feedback and "n = 17" in feedback, feedback
    assert "Add nothing the source does not state" in feedback


@pytest.mark.parametrize("where", WHERE)
@pytest.mark.parametrize("record", ["Suppose b holds. then n = 17.", "Define b, i.e. n = 17.", "Given b holds iff n = 17, does b necessarily hold?",
                                    "Define b to hold iff n equals 17. Does b necessarily hold?", "If n = 17, does b hold?"])
def test_a_figure_the_sentence_still_suspends_keeps_the_counterexample(record, where):
    """The negative controls: a supposition continued by "then", an abbreviation's full stop, a given that is itself a
    definition, the reviewer's faithful question and a conditional question assert no n = 17: W110, the counterexample (b
    false, n not 17), one provider call."""
    outcome, provider = run(DEFINITION_CLAIM, [output(DEFINITION), output(DEFINITION)], where=where, record=record)
    assert len(provider.calls) == 1
    assert outcome.display_status is S.COUNTEREXAMPLE and codes(outcome) == ["W110"]
    cx = counterexample(outcome)
    assert cx["b"] == "false" and cx["n"] != "17"


@pytest.mark.parametrize("text,asserted", [
    ("In this problem n is 17.", True), ("In this question, n = 17.", True), ("In this task n equals 17.", True),
    ("In this exercise n is 17.", True), ("In the problem, n is 17.", True),
    ("In this scenario n is 17.", False),            # a hypothetical frame stays unrecognised
    ("In this case n is 17.", False),
    ("In this problem, if n is 17, b holds.", False),  # the frame presents the task; the condition still governs
    ("In this problem n could be 17.", False),
])
def test_a_frame_that_names_the_task_presents_its_given(text, asserted):
    """The verifier's probes named "Define b to hold iff n equals 17. In this problem n is 17." a case where n is
    asserted, and the reader did not recognise the frame. A frame that names the task itself ("In this problem", "In this
    question", "In this task", "In this exercise") presents what follows as the task's given, as "The problem states"
    already did; a hypothetical frame ("In this scenario") and a construction inside the clause still decide."""
    assert reading(text, 17).asserted is asserted


@pytest.mark.parametrize("where", WHERE)
def test_end_to_end_a_figure_the_task_frame_presents_is_no_verdict(where):
    outcome, provider = run(DEFINITION_CLAIM, [output(DEFINITION), output(DEFINITION)], where=where,
                            record="Define b to hold iff n equals 17. In this problem n is 17.")
    assert outcome.display_status is S.INVALID_FORMALIZATION and len(provider.calls) == 2
    assert any("E110" in d and "In this problem n is 17" in d for d in provider.calls[1].prior_diagnostics)
    outcome, provider = run(DEFINITION_CLAIM, [output(DEFINITION), output(DEFINITION)], where=where,
                            record="Define b to hold iff n equals 17. In this scenario n is 17.")
    assert outcome.display_status is S.COUNTEREXAMPLE and codes(outcome) == ["W110"] and len(provider.calls) == 1


GIVEN_QUESTIONS = [
    ("Given x = 5 and y = 9, is x < y?", 9, 0, True),
    ("Since n = 17, is b true?", 17, 0, True),
    ("Given that n = 17, does b hold?", 17, 0, True),
    ("Because n is 17, does b hold?", 17, 0, True),
    ("Given n = 17, does b hold iff n = 17?", 17, 0, True),
    ("Given n = 17, does b hold iff n = 17?", 17, 1, False),   # the question (and the biconditional) govern what follows the given
    ("If n = 17, is b true?", 17, 0, False),                   # a condition opens the question
    ("Given that n could be 17, does b hold?", 17, 0, False),  # a hedged given: the question governs the whole sentence
    ("Is it true that, given n = 17, b holds?", 17, 0, False),  # the question opens the sentence
    ("When n is 17, does b hold?", 17, 0, False),
    ("Is n equal to 17?", 17, 0, False),
]


@pytest.mark.parametrize("text,value,k,asserted", GIVEN_QUESTIONS)
def test_a_question_opened_by_a_given_does_not_govern_the_given(text, value, k, asserted):
    """A question governs its whole sentence, except a clause that opens it and presents a fact ("Given ...", "Since
    ...", "Because ..."), which ends at its first comma and is asserted (as before a statement or an instruction), unless
    a construction inside it suspends the sentence."""
    r = reading(text, value, k)
    assert r.asserted is asserted, r


@pytest.mark.parametrize("text,given", [
    ("Given c = 3 + 2 × k, what is c when k = 1?", True),       # the given clause states the formula
    ("Since c = 3 + 2 × k, is c above 3?", True),
    ("Given k = 1, is c = 3 + 2 × k?", False),                   # the formula is what the question asks
    ("Is c = 3 + 2 × k?", False),
    ("If c = 3 + 2 × k, what is c?", False),
    ("Given that c could be 3 + 2 × k, is c above 3?", False),   # a hedged given: the question governs the sentence
])
def test_a_formula_in_the_given_of_a_question_is_a_given_and_one_in_the_question_is_not(text, given):
    """The same scope for the whole-content rule of task authority (``relations.stated_relation``): a relation is
    validated by a record that states it as a given, now also in the opening given of a question, and never by a
    formula the question asks about."""
    from epinoic_logic.translate.relations import stated_relation
    prob = Problem.model_validate(problem([{"id": "P", "expr": eq(V("c"), {"op": "add", "args": [R("3"), {"op": "mul", "args": [R("2"), V("k")]}]})}],
                                          {"id": "C", "expr": cmp("gt", V("c"), R("0")), "label": "c is positive"},
                                          (("c", "Real", None), ("k", "Real", None))))
    assert (stated_relation(prob.premises[0].expr, [SourceText("task", "t", text)]) is not None) is given


# =========================================================================== rounded givens ground

ROUNDED_GIVENS = {
    "x is 0.33 to 2 decimal places.": ("0.325", "0.335"),
    "x ≈ 0.33.": ("0.325", "0.335"),
    "x is about 0.33.": ("0.325", "0.335"),
    "Rounded to two decimal places, x = 0.33.": ("0.325", "0.335"),
    "x = 0.33 (2 d.p.).": ("0.325", "0.335"),
    "x is 0.33, correct to 2 decimal places.": ("0.325", "0.335"),
    "x = 0.33 (3 s.f.)": ("0.3295", "0.3305"),
    "x is 0.33 to two decimal places.": ("0.325", "0.335"),
}
X = (("x", "Real", None),)


def _rounded_problem(text, expr, conclusion=None):
    return problem([{"id": "P", "expr": expr, "label": text, "grounding": {"kind": "task_setting", "source_refs": [{"document_id": "task", "excerpt": text}]}}],
                   conclusion or {"id": "C", "expr": cmp("lt", V("x"), R("1/2")), "label": "x is less than one half"}, X)


@pytest.mark.parametrize("encoding", ["exact", "interval"])
@pytest.mark.parametrize("text", list(ROUNDED_GIVENS))
def test_a_rounded_given_grounds_transcribed_exactly_or_at_its_stated_tolerance(text, encoding):
    """The verifier's regression, for every rounding phrasing it tried: the supplied fact transcribed exactly (x = 0.33)
    or at exactly its stated tolerance grounds (the premise is established, no grounding check fails), and the claim the
    stated value supports (x < 1/2) is ENTAILED and released with a faithful review."""
    lo, hi = ROUNDED_GIVENS[text]
    expr = eq(V("x"), R("0.33")) if encoding == "exact" else between(lo, hi)
    claim, report = make("Given the stated value of x, x is less than 1/2.", support=[text], texts=[("task", text)])
    provider = FixtureTranslationProvider({"c": [output(_rounded_problem(text, expr))]})
    reviewer = SemanticReviewer(FixtureReviewProvider({"c": FAITHFUL}))
    outcome = verify_claim(claim, report, Translator(provider, config=CFG), reviewer, config=CFG, signing_key=KEY, key_id="k")
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.ENTAILED
    assert [c for c in outcome.translation.grounding_checks if c.verified is False] == []
    [p] = outcome.translation.problem.premises
    assert p.grounding.verified is True
    assert outcome.verification.ungrounded_dependencies == [] and outcome.verification.unverified_dependencies == []
    assert outcome.release.permitted, outcome.release.unresolved
    if encoding == "interval":
        [check] = [c for c in outcome.translation.grounding_checks if c.method == "figures_in_excerpt"]
        assert check.verified is True and f"it states [{lo}, {hi})" in check.detail, check.detail


#: (record, interval) pairs that are not what the record states.
NOT_STATED_INTERVALS = [
    ("x is 0.33 to 2 decimal places.", "0.3", "0.4"),     # wider than the stated tolerance
    ("x is 0.33 to 2 decimal places.", "0.329", "0.331"),  # narrower
    ("x is 0.33 to 2 decimal places.", "0.33", "0.34"),    # shifted
    ("x is exactly 0.33.", "0.325", "0.335"),             # an exact figure states no interval
    ("x is 0.33.", "0.325", "0.335"),                     # a given figure with no cue states no interval
    ("x ≈ 0.33 and y ≈ 0.43.", "0.325", "0.435"),         # one end from each of two figures
    ("x is 0.33 to 2.", "0.325", "0.335"),                # a range, no precision cue
    ("x is at most 0.33 (2 d.p.).", "0.325", "0.335"),    # a bound: it states no interval around 0.33
    ("x is not 0.33 to 2 decimal places.", "0.325", "0.335"),  # negated where it stands
]


@pytest.mark.parametrize("record,lo,hi", NOT_STATED_INTERVALS)
def test_an_interval_that_is_not_the_stated_tolerance_does_not_ground(record, lo, hi):
    """Negative controls: the excerpt is located, but an interval that is not exactly the tolerance a rounded figure of
    it states is not what it states: the excerpt check fails and the premise is an evidence failure."""
    grounded, checks = check_problem_grounding(Problem.model_validate(_rounded_problem(record, between(lo, hi))),
                                               [SuppliedText(document_id="task", text=record)])
    [p] = grounded.premises
    assert p.grounding.verified is False
    assert any(c.method == "figures_in_excerpt" and c.verified is False for c in checks)


def test_a_task_authority_premise_at_the_stated_tolerance_is_validated_by_the_task_record():
    """The authority path (a task-authority kind with no excerpt, validated against the records): the task record's
    rounded figure validates the interval it states (``numeric_in_task``, the derivation named), and refutes a wider one
    (the task record was given and states no such interval: an evidence failure)."""
    record = "Measured to 2 decimal places, x is 0.33."
    task = TaskRecord.of("t", "r", record)

    def grounded(expr):
        prob = problem([{"id": "P", "expr": expr, "label": "the measured x", "grounding": {"kind": "task_setting"}}],
                       {"id": "C", "expr": cmp("lt", V("x"), R("1/2")), "label": "x is less than one half"}, X)
        return check_problem_grounding(Problem.model_validate(prob), [], task=task)

    checked, checks = grounded(between("0.325", "0.335"))
    assert checked.premises[0].grounding.verified is True
    [check] = [c for c in checks if c.method == "numeric_in_task"]
    assert check.verified is True and "it states [0.325, 0.335)" in check.detail, check.detail
    checked, checks = grounded(between("0.3", "0.4"))
    assert checked.premises[0].grounding.verified is False
    assert any(c.method == "numeric_in_task" and c.verified is False for c in checks)


@pytest.mark.parametrize("record,op,value,established", [
    ("x is not 0.33.", "eq", "0.33", False),
    ("x isn't 0.33.", "eq", "0.33", False),
    ("x was never 0.33.", "eq", "0.33", False),
    ("x does not equal 0.33.", "eq", "0.33", False),
    ("x is not exactly 0.33.", "eq", "0.33", False),
    ("x is 0.33, not 0.34.", "eq", "0.33", True),     # the negation is the other figure's
    ("x is 0.33, not 0.34.", "eq", "0.34", False),
    ("x is not more than 0.34.", "le", "0.34", True),  # a bound phrase states a bound, it negates nothing
    ("x is 0.33.", "eq", "0.33", True),
])
def test_a_figure_its_record_negates_establishes_nothing(record, op, value, established):
    """Found while measuring this repair, on the tree before it too: the excerpt check read a negation only where the figure
    stands ("≠ 0.33", "other than 0.33"), so "x is not 0.33." established x = 0.33. A negation in the figure's own
    predicate ("is not", "isn't", "never", "does not equal", "not exactly") now establishes nothing (an evidence failure),
    while a negation of another figure and a bound phrase ("not more than") keep their readings."""
    prob = problem([{"id": "P", "expr": cmp(op, V("x"), R(value)), "label": record,
                     "grounding": {"kind": "task_setting", "source_refs": [{"document_id": "task", "excerpt": record}]}}],
                   {"id": "C", "expr": cmp("lt", V("x"), R("1")), "label": "x is less than one"}, X)
    grounded, _checks = check_problem_grounding(Problem.model_validate(prob), [SuppliedText(document_id="task", text=record)])
    assert grounded.premises[0].grounding.verified is (True if established else False)


@pytest.mark.parametrize("bounds,established", [
    ((("ge", "0.325"),), True), ((("gt", "0.325"),), False),   # the lower end is included: x > 0.325 is not stated
    ((("lt", "0.335"),), True), ((("le", "0.335"),), True),    # the upper end is excluded: both bounds hold
    ((("ge", "0.3"),), False), ((("lt", "0.34"),), False),     # bounds at other values are not what it states
    ((("ge", "0.325"), ("le", "0.335")), True), ((("gt", "0.325"), ("lt", "0.335")), False),
])
def test_a_stated_interval_establishes_only_the_bounds_at_its_ends(bounds, established):
    record = "x is 0.33 to 2 decimal places."
    args = [cmp(op, V("x"), R(v)) for op, v in bounds]
    expr = args[0] if len(args) == 1 else {"op": "and", "args": args}
    grounded, _checks = check_problem_grounding(Problem.model_validate(_rounded_problem(record, expr)), [SuppliedText(document_id="task", text=record)])
    assert grounded.premises[0].grounding.verified is (True if established else False)


@pytest.mark.parametrize("meaning,lo,hi,established", [
    ("the tax rate as a dimensionless fraction", "0.225", "0.235", True),
    ("the tax rate in per cent", "22.5", "23.5", True),
    ("the tax rate as a dimensionless fraction", "22.5", "23.5", False),
    ("the tax rate in per cent", "0.225", "0.235", False),
    ("the tax rate as a dimensionless fraction", "0.22", "0.24", False),
])
def test_a_rounded_percentage_states_its_interval_in_the_symbol_s_declared_reading(meaning, lo, hi, established):
    """Finding 9 for intervals: "about 23%" states [22.5, 23.5) per cent, which is [0.225, 0.235) as a dimensionless
    fraction, one recorded derivation; the reading the symbol declares decides which, and a wider interval is not stated."""
    record = "The tax rate is about 23%."
    prob = problem([{"id": "P", "expr": {"op": "and", "args": [cmp("ge", V("tax_rate"), R(lo)), cmp("lt", V("tax_rate"), R(hi))]}, "label": record,
                     "grounding": {"kind": "task_setting", "source_refs": [{"document_id": "task", "excerpt": record}]}}],
                   {"id": "C", "expr": cmp("lt", V("tax_rate"), R("1")), "label": "the rate is below one"}, (("tax_rate", "Real", meaning),))
    grounded, _checks = check_problem_grounding(Problem.model_validate(prob), [SuppliedText(document_id="task", text=record)])
    assert grounded.premises[0].grounding.verified is (True if established else False)


def test_the_numeral_of_a_precision_cue_is_no_end_of_a_range():
    """"0.33 to 2 decimal places" states 0.33 (the 2 says how exactly), so the figure is asserted and establishes x =
    0.33; a genuine range ("2 to 3 per cent", "0.33 to 2") still states neither end."""
    for text in ("x is 0.33 to 2 decimal places.", "x is 0.33 to two decimal places.", "x is 0.33 to 3 s.f.", "x is 0.33 to 2 dp."):
        [f] = [f for f in figures_in(SourceText("claim", "c", text)) if f.value == Fraction(33, 100)]
        assert in_precision_cue(text, f.end + 4)
        assert assertion_at(text, f.start, f.end).asserted, text
        assert stated_as(text, f.start, f.end, "eq") is None, text
        assert stated_intervals(f, text) and stated_intervals(f, text)[0][0][:2] in ((Fraction("0.325"), Fraction("0.335")),
                                                                                    (Fraction("0.3295"), Fraction("0.3305")))
    for text, value in (("Growth was 2 to 3 per cent.", 2), ("x is 0.33 to 2.", Fraction(33, 100))):
        [f] = [f for f in figures_in(SourceText("claim", "c", text)) if f.value == value]
        assert assertion_at(text, f.start, f.end).mood == "range" and stated_as(text, f.start, f.end, "eq") is not None


@pytest.mark.parametrize("unit,lo,hi,established", [
    ("x is 0.33 to 2 decimal places. ", "0.325", "0.335", True),                       # every figure states the wanted interval
    ("x is about 0.5 to 2 decimal places, and y is 0.75 (3 s.f.). ", "0.3251", "0.3351", False),  # none does
])
def test_reading_the_stated_intervals_of_a_long_record_stays_linear(unit, lo, hi, established):
    """The tolerance derivation reads the rounded figures of the records (on the authority path, every figure of every
    supplied text and of the task): 100,000 characters of rounded figures are read under 2 s (measured as in
    tests/timing.py), whether every figure states the wanted interval or none does; the scan stops at the first figure
    that establishes what the premise needs, and how a figure is stated is read only for a figure whose interval ends at a
    wanted bound."""
    text = (unit * (100_000 // len(unit) + 1))[:100_000]
    prob = Problem.model_validate(problem([{"id": "P", "expr": between(lo, hi), "label": "x", "grounding": {"kind": "task_setting"}}],
                                          {"id": "C", "expr": cmp("lt", V("x"), R("1")), "label": "x is less than one"}, X))
    task = TaskRecord.of("t", "r", "Find x.")
    timing = measure(lambda: check_problem_grounding(prob, [SuppliedText(document_id="doc", text=text)], task=task), bound=2.0,
                     label="stated intervals")
    assert timing.holds, timing
    grounded, _checks = timing.results[0]
    assert grounded.premises[0].grounding.verified is (True if established else False)


def test_the_retry_the_stated_precision_asks_for_grounds_and_keeps_its_counterexample():
    """The whole repair path of a rounded given whose rounding decides the claim: "x is 0.33 to 2 decimal places, so x is
    less than 1/3". The exact transcription proves it only by ignoring the stated tolerance, so it is rejected (stated
    precision) and fed back; the retry at exactly the stated interval is accepted, its premise is established by the
    supplied text (the excerpt states that interval), and the counterexample at the stated tolerance is the verdict. No
    grounding check fails, and the repair is recorded as supported by the source."""
    text = "x is 0.33 to 2 decimal places."
    conclusion = {"id": "C", "expr": cmp("lt", V("x"), R("1/3")), "label": "x is less than one third"}
    exact = _rounded_problem(text, eq(V("x"), R("0.33")), conclusion)
    stated = _rounded_problem(text, between("0.325", "0.335"), conclusion)
    claim, report = make("x is 0.33 to 2 decimal places, so x is less than 1/3.", support=[text], texts=[("task", text)])
    provider = FixtureTranslationProvider({"c": [output(exact), output(stated)]})
    reviewer = SemanticReviewer(FixtureReviewProvider({"c": FAITHFUL}))
    outcome = verify_claim(claim, report, Translator(provider, config=CFG), reviewer, config=CFG, signing_key=KEY, key_id="k")
    assert len(provider.calls) == 2 and any("stated precision" in d for d in provider.calls[1].prior_diagnostics)
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.COUNTEREXAMPLE
    assert Fraction(counterexample(outcome)["x"]) >= Fraction(1, 3)
    assert [c for c in outcome.translation.grounding_checks if c.verified is False] == []
    assert outcome.translation.problem.premises[0].grounding.verified is True
    [repair] = outcome.translation.repairs
    assert repair.kind == "semantic" and repair.rejected_for == ["stated_precision"] and repair.supported_by_source
    assert not any("grounding" in u for u in outcome.release.unresolved), outcome.release.unresolved
