"""Accuracy round 2: the readers the round adds or changes, each read on its own (the cases of
``tests/data/accuracy_round2_cases.json`` run them through the public pipeline), and each linear in its input (two sizes, a
ratio of CPU times, never a wall-clock bound; ``tests/growth.py``).

* V1I-01 and V1-STANCE-QUADRATIC (EVD-SRC-006): ``diag_evidence._stance_index`` reads, per content word of a document,
  whether every statement that holds it carries each stance, in one pass; ``_stance_object`` reads what the claim's stance
  is about, never its holder.
* V1I-02 (task facts): ``grounding._task_change_clauses`` and ``_held_change_roots`` hold a premise's verb of a change when a
  clause of the task states a change of its direction, in any words, of the premise's own subject; ``_unread_particles``
  reverts the conflict reading of a phrasal verb the closed lists do not hold to no refutation.
* V1I-02 and V1-RESTATE-SUSPENDED (EVD-SRC-001): ``diag_evidence._task_statements`` and ``_asserted_by_task`` read whether
  a sentence the task asserts holds a premise's words; a sentence that suspends them (a report, a hedge, a supposition, an
  expectation) does not, and the premise's own change must be the sentence's.
* V1I-03 and V1-BARE-CIRCULAR (ARG-CIRC-003): ``diag_argument._point_and_reason`` reads a cause phrase as the claim's
  reason.
* V1I-07 (ARG-NS-003): ``diag_argument._own_step``: a join whose reason states a step of the writer's own is no leap.
* V1I-05 (stated rules): ``stated_rules._setting_words`` and the second reading of ``stated_rule``: a rule applied to the case
  the question names is the source's rule; two other cases, a hedged rule and a meaning's own verb are never read so.

Nothing from an input is executed."""
from __future__ import annotations

from epinoic_logic import lexis
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate import diag_argument as DA
from epinoic_logic.translate import diag_evidence as DE
from epinoic_logic.translate import grounding as G
from epinoic_logic.translate import stated_rules as SR
from epinoic_logic.translate.quantities import SourceText
from epinoic_logic.translate.stated_rules import meaning_roots

from ..growth import growth

LINEAR = 8.0  # a 4x input: about 4 for a linear reader, about 16 for a quadratic one
#: the token cache of short texts is emptied before every timed call, so neither size is served from it
CLEAR = lexis._cached_token_spans.cache_clear


def _premise(label: str, negated: bool = False):
    """A label-only task premise (one atom whose meaning is the label) and its symbols, as the IR holds them."""
    var = {"op": "var", "name": "a"}
    problem = Problem.model_validate({
        "ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "a", "sort": "Bool", "meaning": label}],
        "premises": [{"id": "t1", "expr": {"op": "not", "arg": var} if negated else var, "label": label}],
        "conclusion": {"id": "C", "expr": var}})
    return problem.premises[0], {s.name: s for s in problem.symbols}


def _rule(antecedent: str, consequent: str):
    problem = Problem.model_validate({
        "ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "a", "sort": "Bool", "meaning": antecedent}, {"name": "b", "sort": "Bool", "meaning": consequent}],
        "premises": [{"id": "q1", "expr": {"op": "implies", "left": {"op": "var", "name": "a"}, "right": {"op": "var", "name": "b"}}}],
        "conclusion": {"id": "C", "expr": {"op": "var", "name": "b"}}})
    return problem.premises[0].expr, {s.name: s for s in problem.symbols}


def _stated(text: str, antecedent: str, consequent: str):
    expr, symbols = _rule(antecedent, consequent)
    return SR.stated_rule(expr, symbols, SourceText("supplied_text", "ext", text), (0, len(text) - 1))


# ------------------------------------------------------------------------------- V1I-01, V1-STANCE-QUADRATIC

def test_a_stance_is_read_only_where_every_statement_about_its_object_carries_one():
    index = DE._stance_index("Farmers welcomed the heavy rain in April, but the new water tax angered them deeply.")
    # the approving clause speaks of the farmers and the rain; the clause about the tax holds no stance word of the lists
    assert index["farmer"] == (False, True) and index["rain"] == (False, True)
    assert index["tax"] == (True, True) and index["water"] == (True, True)
    # a clause whose stance word governs an object pronoun speaks of what the clause before it names
    assert DE._stance_index("The new water tax was introduced in May. Farmers welcomed it warmly.")["tax"] == (False, True)
    assert DE._stance_index("The new water tax was introduced in May. Farmers paid it promptly.")["tax"] == (True, True)


def test_what_a_stance_is_about_is_what_its_word_governs_never_its_holder():
    assert DE._stance_object("farmers opposed the water tax") == {"water", "tax"}
    assert DE._stance_object("the water tax was opposed by farmers") == {"water", "tax"}  # a passive: the words before it
    # a stance word that ends its clause is about the words after the judging verb, never the holder before it
    assert DE._stance_object("even the German delegate thought the treaty fair") == {"treaty"}
    assert DE._stance_object("the treaty was fair") == {"treaty"}
    assert DE._stance_object("farmers paid the water tax") == set()  # no stance word


def test_the_stance_readers_are_linear_on_a_document_of_distinct_words():
    """The shape of V1-STANCE-QUADRATIC (a long document of distinct words with a stance word in every clause, and one clause
    of distinct words): the round-1 clause reading copied a clause's stems for every stance word."""
    def clauses(n: int) -> str:
        return " ".join(f"condemned q{k}x," for k in range(n))

    def one_clause(n: int) -> str:
        return "welcomed " + " ".join(f"w{k}x condemned" for k in range(n))

    for make in (clauses, one_clause):
        for reader in (DE._stance_index, DE._stances, DE._stance_object):
            ratio, small, large = growth(reader, make(400), make(1600), clear=CLEAR)
            assert ratio < LINEAR, (reader.__name__, make.__name__, ratio, small, large)


# ------------------------------------------------------------------------------- V1I-02: a change in any words

def test_a_change_the_task_states_of_the_premises_subject_in_any_words_holds_the_premises_verb_of_that_direction():
    def clauses(text: str):
        return G._task_change_clauses([SourceText("task", "task", text)])

    def held(label: str, text: str) -> set[str]:
        return G._held_change_roots(label, clauses(text), meaning_roots(label))

    costs = "As wages increased, the firm drove its costs down by automating its factories."
    assert [[up for _s, _e, up in c[2]] for c in clauses(costs)] == [[True], [False]]  # the words of a change of each clause
    assert clauses("Did the firm drive its costs down?") == ()  # a question states nothing
    assert held("the firm lowered its costs", costs) == {"lower"}
    assert held("the firm raised its costs", costs) == set()  # the rise is the wages'
    assert held("the central bank lowered interest rates", "After inflation fell, the central bank raised interest rates.") == set()
    assert held("the supermarket lowered its prices", "As competition grew, the supermarket knocked its prices down.") == {"lower"}
    # in one clause, the change nearest to the premise's words is what the clause says changed about them
    assert held("the central bank lowered interest rates", "The central bank brought interest rates down to boost spending.") == {"lower"}
    assert G.clause_direction(G.change_clause("The central bank brought interest rates down to boost spending"), {"spend"}) is True


def test_a_change_held_in_other_words_stands_for_no_other_missing_word():
    def refuted(label: str, text: str):
        p, symbols = _premise(label)
        return G._words_no_record_holds(p, symbols, [SourceText("task", "task", text)])
    assert refuted("the firm lowered its costs", "As wages increased, the firm drove its costs down.") is None
    # another country or another year beside the verb in other words: refuted, as before the round
    assert refuted("unemployment in Country Y declined in 2022", "Unemployment in Country Z fell in 2022.") is not None
    assert refuted("the government of Country K reduced income tax in 2020", "In 2018 the government of Country K cut income tax.") is not None


def test_a_phrasal_verb_the_lists_do_not_hold_refutes_no_direction_and_the_opposite_listed_verb_still_does():
    assert G._unread_particles(lexis.tokens("the supermarket knocked its prices down"))
    assert not G._unread_particles(lexis.tokens("the bank brought interest rates down"))  # a listed phrasal verb
    assert not G._unread_particles(lexis.tokens("prices went down"))
    assert G._task_conflict("the supermarket raised its prices", "As competition grew, the supermarket knocked its prices down.") is None
    why = G._task_conflict("the firm raised its prices", "The firm cut its prices in 2023.")
    assert why is not None and why[2] is True  # still refutable


def test_the_change_readings_are_linear():
    wanted = meaning_roots("the firm lowered its costs")
    for unit in ("As wages increased, the firm drove its costs down. ", "Did the firm put its prices up? ", "Economists say prices went up. ",
                 "Wages rose, prices rose and rents rose, but output fell. "):
        def read(text: str):
            return G._held_change_roots("the firm lowered its costs", G._task_change_clauses([SourceText("task", "task", text)]), wanted)
        # both sizes below the grounding reader's 400 task sentences read for a reported view, past which a sentence is read
        # as stated (a step in cost per sentence, not a growth)
        ratio, small, large = growth(read, unit * 80, unit * 320, clear=CLEAR)
        assert ratio < LINEAR, (unit, ratio, small, large)


# ------------------------------------------------------------------------------- V1I-02, V1-RESTATE-SUSPENDED

def test_a_premise_whose_words_a_sentence_the_task_asserts_holds_is_read_as_its_restatement():
    wage = "The government raised the minimum wage, and economists say this will reduce hiring. Will prices rise?"
    for task, label in ((wage, "the government raised the minimum wage"),  # the clause before the report is the task's own
                        (wage, "the government increased the minimum wage"),  # in other words
                        ("In 2023 the firm cut its prices by 10%.", "the firm lowered its prices"),
                        ("Sales rose faster than expected in 2023.", "sales rose in 2023"),  # 'than expected' states what happened
                        ("The new bridge, which was expected in 2010, opened in 2015.", "the new bridge opened in 2015"),
                        ("As wages increased, the firm drove its costs down.", "the firm lowered its costs"),  # its subject's fall
                        ("The firm increased its prices; as a result, its sales dropped.", "the firm's sales fell")):  # by a pronoun
        p, symbols = _premise(label)
        assert DE._asserted_by_task(p, symbols, task), (label, task)


def test_a_premise_the_task_states_only_as_expected_reported_supposed_or_otherwise_is_not():
    for task, label in (
            ("The government raised the minimum wage, and economists say this will reduce hiring.", "hiring will fall"),  # a report
            ("In Country Q the central bank kept interest rates unchanged, although commentators had expected it to raise interest rates.",
             "the central bank in Country Q increased interest rates"),  # only expected; its own change is not the task's
            ("Economists expect the central bank to raise interest rates next year.", "the central bank raised interest rates"),
            ("If the central bank raises interest rates, borrowing falls.", "the central bank raised interest rates"),  # a condition
            ("The firm did not raise its prices in 2023.", "the firm raised its prices"),  # the other polarity
            ("After inflation fell, the central bank raised interest rates.", "the central bank lowered interest rates"),  # the fall is another's
            ("Although summer temperatures fell, the mass of the glacier went up.", "the mass of the glacier decreased"),
            # a change held only in other words leaves no other word out
            ("In 2020 the government of Country K cut income tax.", "the government of Country K reduced corporation tax in 2020"),
            ("Unemployment in Country Z fell in 2022.", "unemployment in Country Y declined in 2022")):
        p, symbols = _premise(label)
        assert not DE._asserted_by_task(p, symbols, task), (label, task)
    sentences = DE._task_statements("Commentators had expected the bank to raise rates. Sales rose faster than expected. "
                                     "The expected rise in prices happened in May.")
    # each sentence: (statements (roots, negated, suspended), asserted clauses); 'the expected rise' names a thing
    assert [statements[0][2] for statements, _clauses in sentences] == [True, False, False]
    assert [len(clauses) for _statements, clauses in sentences] == [0, 1, 1]


def test_the_restatement_reading_is_linear():
    p, symbols = _premise("the government increased the minimum wage")
    for unit in ("The government raised the minimum wage, and economists say this will reduce hiring. ",
                 "The bridge, which was expected in 2010, opened in 2015. ", "Sales rose faster than expected. "):
        def read(text: str):
            DE._task_statements.cache_clear()
            return DE._asserted_by_task(p, symbols, text)
        ratio, small, large = growth(read, unit * 50, unit * 200, clear=CLEAR)
        assert ratio < LINEAR, (unit[:30], ratio, small, large)


# ------------------------------------------------------------------------------- V1I-03, V1-BARE-CIRCULAR

def test_a_cause_phrase_is_read_as_the_claims_reason():
    assert DA._point_and_reason("The Berlin Wall fell in 1989 due to the fall of the Berlin Wall in 1989.") == (
        "The Berlin Wall fell in 1989", "the fall of the Berlin Wall in 1989", True)
    assert DA._point_and_reason("Due to the fall of the Berlin Wall in 1989, the Berlin Wall fell in 1989.") == (
        "the Berlin Wall fell in 1989", "the fall of the Berlin Wall in 1989", True)
    assert DA._point_and_reason("The Berlin Wall fell in 1989 because the Soviet Union no longer defended East Germany.")[2] is False
    assert DA._point_and_reason("The Berlin Wall fell in 1989.") is None


def test_the_cause_phrase_reading_is_linear():
    for unit in ("the fall of the wall and ", "a number of "):
        ratio, small, large = growth(DA._point_and_reason, "The wall fell due to " + unit * 60 + "fear.", "The wall fell due to " + unit * 240 + "fear.",
                                     clear=CLEAR)
        assert ratio < LINEAR, (unit, ratio, small, large)


# ------------------------------------------------------------------------------- V1I-07

def test_a_join_whose_reason_states_a_step_of_the_writers_own_is_no_leap():
    a, b = "the Wall Street Crash happened in 1929", "German unemployment rose after 1929"
    assert DA.unbridged_leap_reading(["The Wall Street Crash happened in 1929. The Crash made American banks recall their loans to Germany, "
                                      "so German unemployment rose."], a, b) is None
    assert DA.unbridged_leap_reading(["The Wall Street Crash happened in 1929, so German unemployment rose."], a, b) is not None
    # a month or a number added to the reason is no step of the writer's own
    assert DA.unbridged_leap_reading(["French and Belgian troops occupied the Ruhr in January 1923, so German industrial output fell."],
                                     "French and Belgian troops occupied the Ruhr in 1923", "German industrial output fell in 1923") is not None
    # in a sentence that quotes, the words around the quotation attribute it: no step of the writer's own, and a quotation
    # about another target bridges nothing
    ruhr = "French and Belgian troops occupied the Ruhr in 1923"
    assert DA.unbridged_leap_reading([f'{ruhr}, and Historian K writes that "the occupation of the Ruhr angered German workers", so the Weimar '
                                      "Republic collapsed."], ruhr, "the Weimar Republic collapsed") is not None
    assert DA.unbridged_leap_reading([f'{ruhr}, and Historian K writes that "the occupation of the Ruhr crippled German industry", so German '
                                      "industrial output fell."], ruhr, "German industrial output fell in 1923") is None
    assert DA._own_step(frozenset({"crash", "bank", "loan"}), frozenset({"crash"}), frozenset({"unemploy"}))
    assert not DA._own_step(frozenset({"crash", "1929", lexis.root("october")}), frozenset({"crash"}), frozenset({"unemploy"}))


# ------------------------------------------------------------------------------- V1I-05

def test_a_setting_phrase_is_a_name_or_a_head_noun_and_never_the_meanings_own_verb():
    def setting(meaning: str, excerpt: str) -> set[str]:
        return SR._setting_words(meaning, {lexis.root(t) for t in lexis.tokens(excerpt)})
    assert setting("farmland near the Tamar was damaged in 2021", "When the river floods, farmland is damaged") == {"near", "tamar", "in", "2021"}
    assert setting("borrowing in Country P fell", "If interest rates rise, borrowing falls") == {"in", lexis.root("country"), "p"}
    assert setting("the enzyme denatured in the experiment", "If it is heated, the enzyme denatures") == {"in", lexis.root("experiment")}
    assert setting("the patient in the trial recovered", "If the drug is given, the patient improves") == {"in", "trial"}
    assert setting("farmland near the river was damaged", "When the river floods, farmland near the river is damaged") == set()
    assert setting("prices rose in Country P only", "If demand grows, prices rise") == set()  # 'only' is the rule's content


def test_a_rule_applied_to_the_case_the_question_names_is_the_sources_rule():
    rule = _stated("If interest rates rise, borrowing falls.", "interest rates rise", "borrowing in Country P falls")
    assert rule is not None and rule.qualifier is None
    rule = _stated("When the river floods, farmland is damaged.", "the river floods", "farmland near the Tamar is damaged")
    assert rule is not None and rule.qualifier is None
    # two other cases, a hedged rule applied to a case, and a verb the rule does not state are never read as the rule
    assert _stated("If interest rates rise, borrowing falls.", "interest rates in Country Q rise", "borrowing in Country P falls") is None
    assert _stated("If interest rates rise, borrowing may fall.", "interest rates rise", "borrowing in Country P falls") is None
    assert _stated("If the drug is given, the patient improves.", "the drug is given", "the patient in the trial recovered") is None
    # without a setting the hedged rule is read with its qualifier, as before the round
    hedged = _stated("If interest rates rise, borrowing may fall.", "interest rates rise", "borrowing falls")
    assert hedged is not None and hedged.qualifier is not None


def test_the_setting_reading_is_linear():
    excerpt = {lexis.root(t) for t in lexis.tokens("When the river floods, farmland is damaged")}
    for unit in ("farmland near the Tamar was damaged in 2021 and ", "in the second trial in Country P at the school, ", "near the near the "):
        ratio, small, large = growth(lambda text: SR._setting_words(text, excerpt), unit * 100, unit * 400, clear=CLEAR)
        assert ratio < LINEAR, (unit, ratio, small, large)
