"""Finding 6 of the 12 October 2026 review, repaired: whether a source ASSERTS what an encoding left open is read from
the source's grammar, not from the presence of a numeral or a list of definitional keywords.

The independent verification of the first fix found that natural paraphrases of faithful questions were still read as
assertions, so valid counterexamples were withheld (E110/E111) and the retry feedback asked the translator to add a
premise the source never asserts; a retry that followed it was accepted and displayed ENTAILED for a non sequitur. The
cause: a sentence counted as asserting its figures unless it held a definitional keyword ("define", "let", "iff",
"arbitrary", ...), so a condition ("If n equals 17, b holds"), a question, a possibility ("n could be 17"), a
biconditional ("exactly when", "just when") and a negation all read as assertions, and for E111 any figure the
encoding omitted counted as evidence about the free symbol ("I checked 3 values").

Now (``translate.assertion``, used by ``translate.coverage``) a figure is evidence only when

1. its clause asserts it: no question, instruction, condition (including "when" read as a condition), supposition,
   example, definition, possibility, obligation, intention, hedge, attribution, negation, quantification or
   disjunction governs it (each with a stated scope: the sentence, the coordinate unit, or the two clauses a
   biconditional joins), and it is no end of a range or option of a disjunction;
2. what it states establishes what the encoding compares ("more than 17" establishes no ``n = 17``);
3. it is about the encoding's symbols (the clause names them, or shares the words that describe them; a figure that
   counts something else is not).

Each test pairs the faithful question (its counterexample stands with the advisory W110/W111, one provider call, no
premise requested) with the same encoding against a source that does assert the figure (E110/E111: no verdict, the
asserting clause fed back once). The retry an E110 asks for may add only what that source evidence states
(``precision.added_premise_support``); anything else makes the translation AMBIGUOUS_TRANSLATION, never a verdict.
"""
from __future__ import annotations

import json

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.translate.assertion import Target, assertion_at, link, relation_at, relation_implies
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, TranslationStatus as T, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider
from epinoic_logic.translate.quantities import SourceText, figures_in

from ..timing import measure

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
KEY = b"coverage-assertion-test-key-0123456789"


def V(n):
    return {"op": "var", "name": n}


def I(v):
    return {"op": "int", "value": str(v)}


def eq(a, b):
    return {"op": "eq", "left": a, "right": b}


def output(problem):
    return {"problem": problem, "interpretation": {"reading": "as stated", "glossary": [], "ambiguity_flags": []}, "ambiguous": False,
            "unsupported_reason": None}


def make(claim_text, *, support=None, subject="Mathematics", texts=()):
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="a", subject=subject, task_type="calculation")
    claim = ClaimRecord(**ids, claim_id="c", claim_text=claim_text, claim_role="quantitative" if subject == "Mathematics" else "point",
                        proposed_claim_kind="arithmetic" if subject == "Mathematics" else "formal_logic", supporting_claim_ids=["s"] if support else [])
    claims = [claim] + ([ClaimRecord(**ids, claim_id="s", claim_text=support, claim_role="evidence")] if support else [])
    body = " ".join(c.claim_text for c in claims)
    report = SpecialistReport(**ids, original_response=body, response_sha256=sha256_text(body), claims=claims,
                              supplied_texts=[SuppliedText(document_id=d, text=t) for d, t in texts], created_at="2026-10-12T00:00:00Z")
    return claim, report


def problem(premises, conclusion, symbols):
    return {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
            "symbols": [{"name": n, "sort": s, **({"meaning": m} if m else {})} for n, s, m in symbols], "premises": premises, "conclusion": conclusion}


#: The verifier's encoding: b is DEFINED by n = 17 and the claim concludes b.
DEFINITION = problem([{"id": "D", "expr": {"op": "iff", "left": V("b"), "right": eq(V("n"), I(17))}, "label": "b holds iff n equals 17",
                       "grounding": {"kind": "specialist_inference"}}],
                     {"id": "C", "expr": V("b"), "label": "b necessarily holds"}, (("b", "Bool", None), ("n", "Int", None)))
#: The verifier's E111 encoding: x = 5 is encoded and the conclusion compares x with a y no premise mentions.
FREE = problem([{"id": "P", "expr": eq(V("x"), I(5)), "label": "x equals 5", "grounding": {"kind": "task_setting"}}],
               {"id": "C", "expr": {"op": "lt", "left": V("x"), "right": V("y")}, "label": "x is necessarily less than y"},
               (("x", "Int", None), ("y", "Int", None)))
#: The round-6 shape: a History answer's figure defined, not asserted, with the meaning a translator writes.
HISTORY_MEANING = "seventeen African states became independent in 1960 (literal equality)"
HISTORY = problem([{"id": "pr_states_1960_17", "expr": {"op": "iff", "left": V("states_1960_17"), "right": eq(V("num_states_1960"), I(17))},
                    "label": "seventeen African states became independent in 1960", "grounding": {"kind": "general_knowledge"}}],
                  {"id": "C", "expr": V("states_1960_17"), "label": "the decisive turning point was 1960"},
                  (("states_1960_17", "Bool", HISTORY_MEANING), ("num_states_1960", "Int", HISTORY_MEANING)))


def run(claim_text, encoding, *, support=None, subject="Mathematics", responses=None, texts=()):
    claim, report = make(claim_text, support=support, subject=subject, texts=texts)
    provider = FixtureTranslationProvider({"c": responses if responses is not None else output(encoding)})
    outcome = verify_claim(claim, report, Translator(provider, config=CFG), config=CFG, signing_key=KEY, key_id="k")
    return outcome, provider


def codes(outcome):
    return [d.code for d in outcome.verification.diagnostics] if outcome.verification is not None else []


def counterexample(outcome):
    return {a.symbol: a.value for a in outcome.verification.counterexample.assignments}


# =========================================================================== the verifier's paraphrases (negatives)

VERIFIER_DEFINITION_PARAPHRASES = {
    "conditional if": ("If n equals 17, b holds; so b necessarily holds.", "condition ('If')"),
    "conditional when": ("When n equals 17, b holds. So b necessarily holds.", "condition ('When')"),
    "question": ("Is n equal to 17? If it is, b holds. Hence b holds.", "question ('?')"),
    "modal": ("n could be 17, and b holds just when n is 17, so b holds.", "possibility ('could')"),
    "exactly-when question": ("b holds exactly when n equals 17. Does b necessarily hold? No: b need not hold.", "definition ('exactly when')"),
    "negation": ("n is not 17, but b holds exactly when n is 17, so b holds.", "negation ('not')"),
}


@pytest.mark.parametrize("name", list(VERIFIER_DEFINITION_PARAPHRASES))
def test_a_definition_the_source_only_conditions_asks_allows_or_negates_keeps_its_counterexample(name):
    """The verifier's paraphrases of "define b iff n = 17; does b necessarily hold?": none asserts n = 17, so the
    counterexample (b false, n not 17) is the verdict on the faithful encoding, with the advisory W110; the provider is
    called once (no premise requested), and the coverage note names the construction that asserts nothing."""
    text, construction = VERIFIER_DEFINITION_PARAPHRASES[name]
    outcome, provider = run(text, DEFINITION)
    assert len(provider.calls) == 1, "no retry, so no premise is requested"
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.COUNTEREXAMPLE
    assert outcome.verification.status is S.COUNTEREXAMPLE and codes(outcome) == ["W110"]
    cx = counterexample(outcome)
    assert cx["b"] == "false" and cx["n"] != "17"
    note = next(n for n in outcome.translation.coverage if n.kind == "unasserted_definition")
    assert not note.source_asserted and note.evidence == [] and note.evidence_symbols == []
    assert construction in note.detail, note.detail
    assert "Advisory coverage warnings" in outcome.summary


VERIFIER_FREE_PARAPHRASES = {
    "any integer, an unrelated count": "Given x = 5, x < y for any integer y; I checked 3 values.",
    "each of the integers we pick": "Given x = 5, x < y holds for each of the 2 integers y we pick.",
    "an unrelated comparison count": "Given x = 5, x < y; I compared 12 pairs.",
    "a count of values of y": "Given x = 5, x < y, as I checked for 12 values of y.",
    "y could be 9": "Given x = 5, y could be 9, so x < y.",
    "y is not 9": "Given x = 5 and y not equal to 9, x < y.",
}


@pytest.mark.parametrize("name", list(VERIFIER_FREE_PARAPHRASES))
def test_an_unconstrained_variable_keeps_its_counterexample_whatever_else_the_claim_counts(name):
    """The verifier's E111 cases and their kin: a figure the encoding omits is evidence about the free symbol only when
    an asserting clause states it about that symbol. A count of something else ("3 values", "the 2 integers y we
    pick", "12 pairs") or a figure no clause asserts ("could be 9", "not equal to 9") is none: W111, the counterexample
    (x = 5, y not above 5) stands."""
    outcome, _ = run(VERIFIER_FREE_PARAPHRASES[name], FREE)
    assert outcome.display_status is S.COUNTEREXAMPLE and codes(outcome) == ["W111"]
    cx = counterexample(outcome)
    assert cx["x"] == "5" and int(cx["y"]) <= 5
    note = next(n for n in outcome.translation.coverage if n.kind == "unconstrained_symbol")
    assert not note.source_asserted and note.evidence_symbols == []


def test_the_retry_the_misread_conditional_asked_for_is_never_requested_and_never_earns_entailed():
    """The verifier's violation: the conditional was read as asserting 17, the feedback asked for n = 17 as a premise,
    and the retry that added it (specialist_inference, unchecked) was accepted and displayed ENTAILED for a claim that
    does not follow. The conditional asserts nothing now: the first encoding is accepted, the provider is called once, and
    the faithful COUNTEREXAMPLE (b false, n = 2) is displayed, even with the premise-adding retry queued."""
    added = json.loads(json.dumps(DEFINITION))
    added["premises"].append({"id": "N", "expr": eq(V("n"), I(17)), "label": "n equals 17", "grounding": {"kind": "specialist_inference"}})
    outcome, provider = run("If n equals 17, b holds; so b necessarily holds.", DEFINITION, responses=[output(DEFINITION), output(added)])
    assert len(provider.calls) == 1 and outcome.translation.repairs == []
    assert outcome.display_status is S.COUNTEREXAMPLE and outcome.display_status is not S.ENTAILED
    assert counterexample(outcome) == {"b": "false", "n": "2"}
    assert not outcome.release.permitted


# =========================================================================== paired positives

ASSERTED_DEFINITION_PARAPHRASES = {
    "asserted, then defined": ("n equals 17, and b holds exactly when n equals 17; so b holds.", "'n equals 17'"),
    "asserted and defined in one clause pair": ("Since n equals 17 and b holds iff n equals 17, b holds.", "Since n equals 17"),
    "a count the definition names": ("There are 17 items, so b holds, where b means there are exactly 17 items.", "'There are 17 items'"),
    "a reason": ("Since n is 17, b holds.", "Since n is 17"),
    "a given": ("Given that n = 17, b holds.", "Given that n = 17"),
    "a separate statement": ("n = 17. b holds exactly when n = 17. So b holds.", "'n = 17'"),
}


@pytest.mark.parametrize("name", list(ASSERTED_DEFINITION_PARAPHRASES))
def test_a_definition_whose_figure_the_source_asserts_is_no_verdict_and_the_asserting_clause_is_fed_back(name):
    """The pair: the same encoding against sources that do assert n = 17. The encoding omitted an assertion its source
    makes: E110, INVALID_FORMALIZATION, fed back once with the asserting clause as the reason (never the definitional
    clause, and never that entailment would follow)."""
    text, clause = ASSERTED_DEFINITION_PARAPHRASES[name]
    outcome, provider = run(text, DEFINITION)
    assert outcome.translation.status is T.INVALID_FORMALIZATION and outcome.display_status is S.INVALID_FORMALIZATION
    assert len(provider.calls) == 2
    feedback = "\n".join(provider.calls[1].prior_diagnostics)
    assert "E110" in feedback and "the source asserts that figure" in feedback and clause in feedback, feedback
    assert "Add nothing the source does not state" in feedback and "ENTAILED" not in feedback
    note = next(n for n in outcome.translation.coverage if n.kind == "unasserted_definition")
    assert note.source_asserted and note.evidence_symbols == ["n"] and note.source_refs
    assert all("exactly when" not in (r.excerpt or "") and " iff " not in (r.excerpt or "") for r in note.source_refs), note.source_refs


ASSERTED_FREE_PARAPHRASES = {
    "a bound": "Given x = 5 and y > 7, x < y.",
    "a value": "Since x = 5 and y = 9, x < y.",
    "in words": "x is 5 and y is 9, so x < y.",
}


@pytest.mark.parametrize("name", list(ASSERTED_FREE_PARAPHRASES))
def test_a_free_symbol_whose_value_the_source_asserts_is_no_verdict(name):
    outcome, _ = run(ASSERTED_FREE_PARAPHRASES[name], FREE)
    assert outcome.display_status is S.INVALID_FORMALIZATION and codes(outcome) == ["E111"]
    note = next(n for n in outcome.translation.coverage if n.kind == "unconstrained_symbol")
    assert note.source_asserted and note.evidence_symbols == ["y"]


HISTORY_PAIRS = [
    # (supporting claim, the source asserts the defined figure)
    ("In 1960 seventeen African states became independent.", True),
    ("The year 1960 saw seventeen African states become independent.", True),
    ("In 1960, when seventeen African states became independent, the pace changed.", True),
    ("Independence came to seventeen African states in 1960.", True),
    ("If seventeen African states became independent in 1960, that year was decisive.", False),
    ("Some historians claim that seventeen African states became independent in 1960.", False),
    ("Perhaps seventeen African states became independent in 1960.", False),
    ("Did seventeen African states become independent in 1960?", False),
    ("Seventeen African states may have become independent in 1960.", False),
    ("More than seventeen African states became independent in 1960.", False),
    ("Between fifteen and seventeen African states became independent in 1960.", False),
    ("Seventeen or eighteen African states became independent in 1960.", False),
    ("Seventeen delegates attended the 1960 conference.", False),
    ("Had seventeen African states become independent in 1960, the pace would have changed.", False),
]


@pytest.mark.parametrize("support,asserted", HISTORY_PAIRS)
def test_a_history_answer_asserts_its_figure_only_in_a_clause_that_states_it_as_a_fact(support, asserted):
    """The round-6 shape with the meaning and label a translator writes: the figure is source-asserted (E110) only when
    a supporting claim states seventeen African states as a fact; a condition, an attribution, a hedge, a question, a
    possibility, a bound, a range, a disjunction, a counterfactual or a count of something else (delegates) leaves the
    counterexample standing with W110."""
    outcome, provider = run("The decisive turning point was 1960.", HISTORY, support=support, subject="History")
    if asserted:
        assert outcome.display_status is S.INVALID_FORMALIZATION and len(provider.calls) == 2
        assert any("E110" in d and "seventeen" in d for d in provider.calls[1].prior_diagnostics)
    else:
        assert outcome.display_status is S.COUNTEREXAMPLE and codes(outcome) == ["W110"] and len(provider.calls) == 1


# =========================================================================== what is stated, and about whom

def test_what_a_figure_states_must_establish_the_comparison_the_encoding_defines():
    """"more than 17" asserts n > 17, which establishes no n = 17 (the counterexample, n not 17, is consistent with it):
    W110. "nearly 790,000" establishes n < 790000, the comparison a definition 'nearly 790,000' encodes: E110 for that
    definition, and W110 for one that encodes n = 790000."""
    outcome, provider = run("n is more than 17, and b holds exactly when n is 17, so b holds.", DEFINITION)
    assert outcome.display_status is S.COUNTEREXAMPLE and codes(outcome) == ["W110"] and len(provider.calls) == 1
    meaning = "nearly 790,000 people entered the United States in 1882 (literal strict bound below 790,000)"

    def arrivals(op):
        return problem([{"id": "A", "expr": {"op": "iff", "left": V("near_790k"), "right": {"op": op, "left": V("num_1882"), "right": I(790000)}},
                         "label": "1882 alone brought nearly 790,000", "grounding": {"kind": "general_knowledge"}}],
                       {"id": "C", "expr": V("near_790k"), "label": "arrivals were near their peak"},
                       (("near_790k", "Bool", meaning), ("num_1882", "Int", meaning)))
    support = "About 5.2 million people entered the United States in the 1880s, and 1882 alone brought nearly 790,000."
    outcome, provider = run("Arrivals were near their peak.", arrivals("lt"), support=support, subject="History")
    assert outcome.display_status is S.INVALID_FORMALIZATION and len(provider.calls) == 2
    outcome, provider = run("Arrivals were near their peak.", arrivals("eq"), support=support, subject="History")
    assert outcome.display_status is S.COUNTEREXAMPLE and codes(outcome) == ["W110"]


def test_a_figure_about_something_else_is_no_evidence():
    """A figure equal to the defined literal is evidence only when it is about the definition's symbols: "I checked 17
    cases" counts cases, which nothing in the encoding or the source ties to n."""
    outcome, provider = run("I checked 17 cases. b holds exactly when n equals 17, so b holds.", DEFINITION)
    assert outcome.display_status is S.COUNTEREXAMPLE and codes(outcome) == ["W110"] and len(provider.calls) == 1
    note = next(n for n in outcome.translation.coverage if n.kind == "unasserted_definition")
    assert "not about b, n" in note.detail


READINGS = [
    # (text, figure as written, asserted, mood of the construction that decides)
    ("If n equals 17, b holds.", "17", False, "condition"),
    ("When n equals 17, b holds.", "17", False, "condition"),
    ("b holds when n is 17.", "17", False, "condition"),
    ("In 1960, when seventeen African states became independent, the pace changed.", "seventeen", True, "asserted"),
    ("The constraint was still binding when sterling was devalued from $4.03 to $2.80 on 18 September 1949.", "$4.03", True, "asserted"),
    ("The constraint was still binding when sterling was devalued from $4.03 to $2.80 on 18 September 1949.", "$2.80", True, "asserted"),
    ("Is n equal to 17?", "17", False, "question"),
    ("Had n been 17, b would hold.", "17", False, "question"),
    ("Define b to hold iff n equals 17.", "17", False, "instruction"),
    ("Suppose n is 17.", "17", False, "supposition"),
    ("Suppose b holds. Then n is 17.", "17", False, "supposition"),
    ("For example, n is 17.", "17", False, "example"),
    ("b holds exactly when n is 17.", "17", False, "definition"),
    ("n equals 17 and b holds iff n equals 17.", "17", True, "asserted"),
    ("n could be 17.", "17", False, "possibility"),
    ("n must be 17 for b to hold.", "17", False, "possibility"),
    ("The target is 17 states.", "17", False, "possibility"),
    ("Some historians argue that 17 states became independent.", "17", False, "attribution"),
    ("n is not 17.", "17", False, "negation"),
    ("No 17 states became independent.", "17", False, "negation"),
    ("n is 17 and nothing else.", "17", True, "asserted"),
    ("x < y for any integer y and 17 states.", "17", False, "quantified"),
    ("n is 17 or 18.", "17", False, "disjunction"),
    ("Between 15 and 17 states joined.", "17", False, "range"),
    ("Growth was 2 to 3 per cent.", "2", False, "range"),
    ("n ≠ 17.", "17", False, "negation"),
    ("The rate fell from $4.03 to $2.80.", "$4.03", True, "asserted"),
    ("Since n is 17, b holds.", "17", True, "asserted"),
    ("Given that n = 17, b holds.", "17", True, "asserted"),
    ("The vote was No in 17 districts.", "17", True, "asserted"),
]


@pytest.mark.parametrize("text,written,asserted,mood", READINGS)
def test_the_reader_names_the_construction_that_decides_each_figure(text, written, asserted, mood):
    [figure] = [f for f in figures_in(SourceText("claim", "c", text)) if f.written == written][:1]
    reading = assertion_at(text, figure.start, figure.end)
    assert (reading.asserted, reading.mood) == (asserted, mood), reading


RELATIONS = [
    ("more than 17 states", "gt"), ("over 17 states", "gt"), ("at least 17 states", "ge"), ("17 or more states", "ge"),
    ("fewer than 17 states", "lt"), ("nearly 790,000 arrivals", "lt"), ("at most 17 states", "le"), ("up to 17 states", "le"),
    ("capped at 17 states", "le"), ("about 17 states", "approx"), ("17 states", "eq"), ("exactly 17 states", "eq"),
]


@pytest.mark.parametrize("text,relation", RELATIONS)
def test_the_reader_reads_what_a_figure_states_about_its_value(text, relation):
    [figure] = figures_in(SourceText("claim", "c", text))
    assert relation_at(text, figure.start, figure.end) == relation


def test_a_stated_relation_establishes_only_the_comparisons_it_implies():
    assert relation_implies("eq", "eq") and relation_implies("approx", "eq") and relation_implies("eq", "le")
    assert relation_implies("lt", "lt") and relation_implies("lt", "le") and relation_implies("gt", "ge")
    assert not relation_implies("gt", "eq") and not relation_implies("lt", "eq") and not relation_implies("ge", "eq")
    assert not relation_implies("le", "lt") and not relation_implies("eq", "lt") and relation_implies("gt", None)


def test_a_figure_links_to_symbols_by_name_by_their_words_or_by_what_it_counts():
    def linked(text, written, target):
        [f] = [f for f in figures_in(SourceText("claim", "c", text)) if f.written == written]
        return link(text, f.start, f.end, assertion_at(text, f.start, f.end).unit, target)
    n = Target(names=("b", "n"), words=frozenset(), named=True)
    assert linked("n equals 17", "17", n) and linked("the count n is 17", "17", n)
    assert linked("I checked 17 cases", "17", n) is None  # it counts cases, and nothing says n counts them
    items = Target(names=("b", "n"), words=frozenset({"item"}), named=True)
    assert linked("There are 17 items", "17", items)
    y = Target(names=("y",), words=frozenset(), named=True)
    assert linked("y = 9", "9", y) and linked("the 2 integers y we pick", "2", y) is None and linked("I tried 3 values", "3", y) is None
    states = Target(names=("num_states_1960",), words=frozenset({"african", "stat", "independent", "1960"}), named=False)
    assert linked("In 1960 seventeen African states became independent.", "seventeen", states)
    assert linked("Seventeen delegates attended the 1960 conference.", "Seventeen", states) is None
    # nothing describes the symbols and no source names them: the value is the only link the encoding offers
    bare = Target(names=("b", "n"), words=frozenset(), named=False)
    assert linked("In 1960 seventeen African states became independent.", "seventeen", bare)
    assert linked("I checked 17 values.", "17", bare) is None  # a generic count is still no value of a symbol


# =========================================================================== the retry an E110 asks for

ASSERTING = "n equals 17, and b holds exactly when n equals 17; so b holds."


def _retry(*premises):
    data = json.loads(json.dumps(DEFINITION))
    data["symbols"].append({"name": "m", "sort": "Int"})
    data["premises"] += list(premises)
    return data


def test_a_retry_that_adds_the_asserted_figure_is_a_translation_of_the_claim():
    """Control: the source asserts n = 17, the encoding only defined it, E110 asked for the asserted figure, and the retry
    adds exactly that. The semantic repair is supported by the source and the claim follows (formal ENTAILED; release
    stays refused: the added premise is the specialist's own, unchecked)."""
    stated = _retry({"id": "N", "expr": eq(V("n"), I(17)), "label": "n equals 17", "grounding": {"kind": "specialist_inference"}})
    outcome, provider = run(ASSERTING, DEFINITION, responses=[output(DEFINITION), output(stated)])
    assert len(provider.calls) == 2 and outcome.translation.status is T.TRANSLATED and outcome.display_status is S.ENTAILED
    [repair] = outcome.translation.repairs
    assert repair.kind == "semantic" and repair.rejected_for == ["unasserted_figure"] and repair.conclusion == "unchanged"
    assert repair.supported_by_source and any(c.startswith("premise N supported") for c in repair.changes)
    assert not outcome.release.permitted
    # a reformulated definition (n = 17 -> b) beside the stated figure adds nothing the source does not state
    reformulated = _retry({"id": "D2", "expr": {"op": "implies", "left": eq(V("n"), I(17)), "right": V("b")}},
                          {"id": "N", "expr": eq(V("n"), I(17))})
    outcome, _ = run(ASSERTING, DEFINITION, responses=[output(DEFINITION), output(reformulated)])
    assert outcome.translation.status is T.TRANSLATED and outcome.translation.repairs[0].supported_by_source


@pytest.mark.parametrize("name,premises", [
    ("an invented figure beside the stated one", [{"id": "N", "expr": eq(V("n"), I(17))}, {"id": "M", "expr": eq(V("m"), I(4))}]),
    ("the figure reached through an invented one", [{"id": "M", "expr": eq(V("m"), I(17))}, {"id": "L", "expr": eq(V("n"), V("m"))}]),
])
def test_a_retry_that_adds_what_the_source_does_not_assert_never_earns_a_verdict(name, premises):
    """A retry after E110 may add only what that rejection's source evidence states. A premise that does not follow from
    the earlier premises with the asserted atom, and that no check established, earned its ENTAILED with something no
    source asserts: AMBIGUOUS_TRANSLATION with the flag retry_added_premise, never displayed as ENTAILED, release refused
    with the reason."""
    outcome, provider = run(ASSERTING, DEFINITION, responses=[output(DEFINITION), output(_retry(*premises))])
    assert len(provider.calls) == 2
    assert outcome.verification is not None and outcome.verification.status is S.ENTAILED  # the encoding alone would prove
    assert outcome.translation.status is T.AMBIGUOUS_TRANSLATION and outcome.display_status is S.AMBIGUOUS_TRANSLATION
    assert outcome.display_status is not S.ENTAILED
    flag = next(f for f in outcome.translation.interpretation.ambiguity_flags if f.code == "retry_added_premise")
    assert "may add only what the source asserts" in flag.message
    [repair] = outcome.translation.repairs
    assert not repair.supported_by_source and any("unsupported, NOT what the source asserts" in c for c in repair.changes)
    assert not outcome.release.permitted and any("a retry added premises no source asserts" in u for u in outcome.release.unresolved)


def test_a_later_rejection_of_another_kind_does_not_hide_what_the_e110_asked_for():
    """With more attempts allowed, a rejection for another reason (here a circular encoding, E112) between the E110 and
    the accepted attempt does not reset the check: every premise the accepted attempt adds is checked against the E110's
    source evidence, so an invented premise still makes the translation AMBIGUOUS_TRANSLATION."""
    circular = json.loads(json.dumps(DEFINITION))
    circular["premises"].append({"id": "A", "expr": V("b"), "label": "b holds", "grounding": {"kind": "assumption"}})
    invented = _retry({"id": "N", "expr": eq(V("n"), I(17))}, {"id": "M", "expr": eq(V("m"), I(4))})
    claim, report = make(ASSERTING)
    provider = FixtureTranslationProvider({"c": [output(DEFINITION), output(circular), output(invented)]})
    outcome = verify_claim(claim, report, Translator(provider, config=CFG, max_attempts=3), config=CFG, signing_key=KEY, key_id="k")
    assert len(provider.calls) == 3
    assert any("E110" in d for d in provider.calls[1].prior_diagnostics) and any("E112" in d for d in provider.calls[2].prior_diagnostics)
    assert outcome.translation.status is T.AMBIGUOUS_TRANSLATION and outcome.display_status is S.AMBIGUOUS_TRANSLATION
    assert any(f.code == "retry_added_premise" for f in outcome.translation.interpretation.ambiguity_flags)
    [repair] = outcome.translation.repairs
    assert repair.rejected_for == ["unasserted_figure", "circular"] and not repair.supported_by_source
    assert any(c.startswith("premise M unsupported") for c in repair.changes)


def test_a_retry_may_add_a_premise_a_check_established():
    """A premise grounded in a supplied text whose excerpt the grounding check locates is established in this process:
    the retry may add it, though the rejection's evidence did not name it."""
    doc = "Measured value: m equals 4."
    established = _retry({"id": "N", "expr": eq(V("n"), I(17))},
                         {"id": "M", "expr": eq(V("m"), I(4)), "grounding": {"kind": "supplied_text", "source_refs": [{"document_id": "doc", "excerpt": "m equals 4"}]}})
    outcome, _ = run(ASSERTING, DEFINITION, responses=[output(DEFINITION), output(established)], texts=[("doc", doc)])
    assert outcome.translation.status is T.TRANSLATED and outcome.display_status is S.ENTAILED
    [repair] = outcome.translation.repairs
    assert repair.supported_by_source and any(c.startswith("premise M supported: established by a grounding check") for c in repair.changes)


# =========================================================================== cost on untrusted text

PATHOLOGICAL = {
    "conditions and assertions": "If n is 17, b holds, and n is 17; ",
    "temporal and conditional when": "x = 5 when y was 9, so z is 3. When w is 4, v holds. ",
    "biconditionals, disjunctions and ranges": "n iff 17, and 17 or 18 between 15 and 17. ",
    "many coordinate units": "one, and two, but three, so 4, hence 5: 6. ",
}


@pytest.mark.parametrize("name", list(PATHOLOGICAL))
def test_reading_every_figure_of_a_long_untrusted_text_stays_linear(name):
    """100,000 characters: every figure's assertion, relation and link read under 2 s, measured as in tests/timing.py (a
    warm-up, then the median of five runs, each a first reading with the package's caches emptied)."""
    text = (PATHOLOGICAL[name] * (100_000 // len(PATHOLOGICAL[name]) + 1))[:100_000]
    target = Target(names=("n", "b"), words=frozenset({"state"}), named=True)

    def read_all():
        out = []
        for f in figures_in(SourceText("supplied_text", "long", text)):
            reading = assertion_at(text, f.start, f.end)
            out.append((reading.asserted, relation_at(text, f.start, f.end), link(text, f.start, f.end, reading.unit, target) is not None))
        return len(out), sum(1 for a, _r, _l in out if a)

    timing = measure(read_all, bound=2.0, label=name)
    assert timing.holds, timing
    assert all(r == timing.results[0] for r in timing.results), "every run reads the same figures the same way"
    count, asserted = timing.results[0]
    assert count > 3_000 and 0 <= asserted <= count


def test_the_translation_prompt_says_a_conditioned_figure_is_not_asserted():
    """The prompt in use agrees with the pipeline's rule: a figure the source only conditions, asks about, allows,
    negates, quantifies or attributes is not asserted, and a condition is encoded as a condition, never as a premise."""
    from epinoic_logic.translate import prompts
    text = prompts.load_prompt(prompts.TRANSLATE_PROMPT_VERSION)
    for needle in ("only conditions", '"when n is 17"', "allows", "negates", "encode the condition", "never as a premise",
                   "Never add a premise the source does not state"):
        assert needle in text, needle
