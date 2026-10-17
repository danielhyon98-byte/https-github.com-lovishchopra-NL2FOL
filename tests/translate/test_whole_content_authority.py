"""Finding 2 of the 12 October 2026 review, second repair: no check confers task or source authority on a premise unless it
verifies the premise's whole content.

The independent verification of the first repair found the reviewer's literal checks passing (the 160 km substitution
refuted under every trusted kind, the authentic 120 still supporting 15) while the cause stayed open: the authority check
(``numeric_in_task``) and the excerpt check (``figures_in_excerpt``) verified a premise once its NUMERALS occurred in a
record, never its relation. Its probe: the task "A car travels 120 km in 8 hours", ``d = 120`` and an invented, wrong
formula ``speed = d * 8`` proving "The speed is 960 km/h". Labelled ``arithmetic_fact``, ``task_setting`` or
``rubric_rule``, the formula was "verified" because 8 occurs in the task, hidden from both dependency lists, and release
was permitted with a faithful review; labelled ``general_knowledge`` or ``assumption`` it was listed and blocked release.
The model's label still decided whether an unsupported premise was hidden.

Now (``translate.relations``, used by ``translate.grounding``) a premise's numeric content is an ASSIGNMENT (each conjunct
compares one symbol with one literal) or a RELATION (anything else). A record verifies an assignment when it states the
figure, typed, so that it establishes the comparison ("more than 17" establishes no ``n = 17``); it verifies a relation
only when it states that same relation as a formula, as a given (``relation_in_source``). Figures occurring in a record
never verify a relation, whatever its kind, and a located excerpt holding them does not either: the relation is the
translation's own, an unverified dependency that blocks release. The formal status is reported unchanged.
"""
from __future__ import annotations

import json

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, TaskRecord, TranslationStatus as T, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.relations import formulas_in, numeric_shape, relation_key, stated_relation
from epinoic_logic.translate.quantities import SourceText
from epinoic_logic.translate.review import SemanticReviewer
from epinoic_logic.ir.schema import Problem

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
KEY = b"whole-content-authority-test-key-0123456789"
FAITHFUL = {"verdict": "faithful", "issues": []}


def V(n):
    return {"op": "var", "name": n}


def R(v):
    return {"op": "real", "value": str(v)}


def I(v):
    return {"op": "int", "value": str(v)}


def eq(a, b):
    return {"op": "eq", "left": a, "right": b}


def cmp(op, a, b):
    return {"op": op, "left": a, "right": b}


def output(problem):
    return {"problem": problem, "interpretation": {"reading": "as stated", "glossary": [], "ambiguity_flags": []}, "ambiguous": False,
            "unsupported_reason": None}


def problem(premises, conclusion, symbols):
    return {"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
            "symbols": [dict(name=n, sort=s, **({"meaning": m} if m else {})) for n, s, m in symbols], "premises": premises, "conclusion": conclusion}


def make(claim_text, *, support=(), texts=(), subject="Physics"):
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="a", subject=subject, task_type="calculation")
    supporting = [ClaimRecord(**ids, claim_id=f"s{i}", claim_text=t, claim_role="evidence") for i, t in enumerate(support)]
    claim = ClaimRecord(**ids, claim_id="c", claim_text=claim_text, claim_role="quantitative", proposed_claim_kind="arithmetic",
                        supporting_claim_ids=[c.claim_id for c in supporting])
    body = " ".join([claim_text, *support])
    report = SpecialistReport(**ids, original_response=body, response_sha256=sha256_text(body), claims=[claim, *supporting],
                              supplied_texts=[SuppliedText(document_id=d, text=t) for d, t in texts], created_at="2026-10-16T00:00:00Z")
    return claim, report


def run(claim, report, responses, *, task=None, review=FAITHFUL, max_attempts=2):
    provider = FixtureTranslationProvider({"c": responses})
    reviewer = SemanticReviewer(FixtureReviewProvider({"c": review})) if review is not None else None
    outcome = verify_claim(claim, report, Translator(provider, config=CFG, max_attempts=max_attempts), reviewer, config=CFG, signing_key=KEY,
                           key_id="k", task=task)
    return outcome, provider


def checks_on(outcome, target):
    return [(c.method, c.verified) for c in outcome.translation.grounding_checks if c.target_id == target]


# =========================================================================== the verifier's probe (f2b) and its class

CAR_TASK = "A car travels 120 km in 8 hours. Find its average speed in km/h."
CAR_TEXT = "Distance 120 km over 8 hours."
CAR_SYMBOLS = (("d", "Real", "distance in km"), ("speed", "Real", "speed in km/h"))


def car(formula, kind, concl):
    return problem([{"id": "D", "expr": eq(V("d"), R(120)), "label": "Distance is 120 km", "grounding": {"kind": "arithmetic_fact"}},
                    {"id": "SPEED", "expr": eq(V("speed"), formula), "label": "speed from distance and time", "grounding": kind}],
                   {"id": "C", "expr": eq(V("speed"), R(concl))}, CAR_SYMBOLS)


TIMES_8 = {"op": "mul", "args": [V("d"), R(8)]}
OVER_8 = {"op": "div", "left": V("d"), "right": R(8)}


@pytest.mark.parametrize("kind", ["arithmetic_fact", "task_setting", "rubric_rule"])
def test_the_verifiers_invented_formula_is_an_unverified_dependency_whatever_its_trusted_kind(kind):
    """The verifier's probe f2b: the wrong formula speed = d * 8 proves 960 km/h. Its figure 8 occurs in the task and in
    the supplied text, which verified it before; now no check establishes it: the formal ENTAILED is reported as such,
    SPEED is listed as an unverified dependency in the signed result, the summary names it as an unverified relation, and
    release is refused with it as a reason, even with a faithful review."""
    claim, report = make("The speed is 960 km/h.", support=[CAR_TEXT], texts=[("doc", CAR_TEXT)])
    outcome, _ = run(claim, report, output(car(TIMES_8, {"kind": kind}, 960)), task=TaskRecord.of("t", "r", CAR_TASK))
    assert outcome.display_status is S.ENTAILED  # the encoding's formal result, never hidden or upgraded
    v = outcome.verification
    assert v.premises_relied_on == ["D", "SPEED"]
    assert v.ungrounded_dependencies == [] and v.unverified_dependencies == ["SPEED"]
    assert ("relation_in_source", None) in checks_on(outcome, "SPEED")
    assert not any(verified is True for _m, verified in checks_on(outcome, "SPEED"))
    assert ("numeric_in_task", True) in checks_on(outcome, "D")  # the stated figure itself is still validated
    assert outcome.semantic_review.verdict == "faithful" and not outcome.release.permitted and not outcome.release.evidence_resolved
    assert any("SPEED" in u for u in outcome.release.unresolved)
    assert "Unverified relations" in outcome.summary and "SPEED" in outcome.summary


@pytest.mark.parametrize("kind", ["general_knowledge", "assumption"])
def test_the_same_formula_under_an_untrusted_kind_stays_ungrounded(kind):
    """Control: under the writer's own kinds the formula was always listed (ungrounded); it still is, and the label no
    longer decides whether it is listed at all."""
    claim, report = make("The speed is 960 km/h.", support=[CAR_TEXT], texts=[("doc", CAR_TEXT)])
    outcome, _ = run(claim, report, output(car(TIMES_8, {"kind": kind}, 960)), task=TaskRecord.of("t", "r", CAR_TASK))
    assert outcome.display_status is S.ENTAILED
    assert outcome.verification.ungrounded_dependencies == ["SPEED"] and outcome.verification.unverified_dependencies == []
    assert not outcome.release.permitted


@pytest.mark.parametrize("kind,listed", [("supplied_text", "unverified"), ("quotation", "ungrounded")])
def test_a_located_excerpt_holding_the_relations_figures_does_not_establish_it(kind, listed):
    """The excerpt path of the same class: the formula grounded by the located excerpt "Distance 120 km over 8 hours." (its
    figure 8 is there) is not stated by it; the reference is located, the relation is not verified."""
    claim, report = make("The speed is 960 km/h.", support=[CAR_TEXT], texts=[("doc", CAR_TEXT)])
    grounding = {"kind": kind, "source_refs": [{"document_id": "doc", "excerpt": CAR_TEXT}]}
    outcome, _ = run(claim, report, output(car(TIMES_8, grounding, 960)), task=TaskRecord.of("t", "r", CAR_TASK))
    methods = checks_on(outcome, "SPEED")
    assert ("verbatim_match", True) in methods and ("relation_in_source", None) in methods
    v = outcome.verification
    assert "SPEED" in (v.unverified_dependencies if listed == "unverified" else v.ungrounded_dependencies)
    assert not outcome.release.permitted


@pytest.mark.parametrize("formula,concl", [(OVER_8, 15), (TIMES_8, 960)])
def test_figures_in_the_task_establish_neither_the_authentic_nor_the_invented_formula(formula, concl):
    """The check cannot tell the authentic speed = d / 8 from the invented speed = d * 8 by their figures, so it confers
    authority on neither: both are the translation's own relations (formal verdicts reported, release refused)."""
    claim, report = make(f"The speed is {concl} km/h.", support=[CAR_TEXT], texts=[("doc", CAR_TEXT)])
    outcome, _ = run(claim, report, output(car(formula, {"kind": "arithmetic_fact"}, concl)), task=TaskRecord.of("t", "r", CAR_TASK))
    assert outcome.display_status is S.ENTAILED
    assert outcome.verification.unverified_dependencies == ["SPEED"] and not outcome.release.permitted


# =========================================================================== a relation a record states (positive control)

RIDE = (("c", "Real", "cost of the ride in dollars"), ("k", "Real", "length of the ride in km"))


def ride(rel, concl, kind=None):
    return problem([{"id": "K", "expr": eq(V("k"), R(10)), "label": "the ride is 10 km", "grounding": {"kind": "arithmetic_fact"}},
                    {"id": "COST", "expr": rel, "label": "the fare rule", "grounding": kind or {"kind": "task_setting"}}],
                   {"id": "C", "expr": eq(V("c"), R(concl))}, RIDE)


def fare(a, b):  # c = a + b * k
    return eq(V("c"), {"op": "add", "args": [R(a), {"op": "mul", "args": [R(b), V("k")]}]})


GIVEN_RULE = "Let c = 3 + 2 × k for a ride of k km. Find the cost of a 10 km ride."


@pytest.mark.parametrize("rel", [fare(3, 2), eq(V("c"), {"op": "add", "args": [{"op": "mul", "args": [V("k"), R(2)]}, R(3)]})],
                         ids=["as written", "terms reordered"])
def test_a_relation_the_task_gives_is_established_and_release_follows_the_review(rel):
    """The positive control: the task gives the fare rule ("Let c = 3 + 2 × k"), so the relation is verified against it
    (in any order of terms), the stated 10 km verifies k = 10, every relied-on premise is established, and the faithful
    review permits release."""
    claim, report = make("The ride costs 23 dollars.", subject="Mathematics")
    outcome, _ = run(claim, report, output(ride(rel, 23)), task=TaskRecord.of("t", "r", GIVEN_RULE))
    assert outcome.display_status is S.ENTAILED
    assert ("relation_in_source", True) in checks_on(outcome, "COST") and ("numeric_in_task", True) in checks_on(outcome, "K")
    assert outcome.verification.ungrounded_dependencies == [] and outcome.verification.unverified_dependencies == []
    assert outcome.release.permitted, outcome.release.unresolved


def test_an_invented_rule_beside_a_given_one_is_not_established():
    """Negative control of the pair: with the same task, a premise that invents another rule (c = 3 + 4 × k) is refuted
    (its figure 4 is stated nowhere) and never established; release is refused."""
    claim, report = make("The ride costs 43 dollars.", subject="Mathematics")
    outcome, _ = run(claim, report, output(ride(fare(3, 4), 43)), task=TaskRecord.of("t", "r", GIVEN_RULE))
    assert outcome.display_status is S.ENTAILED
    assert "COST" in outcome.verification.ungrounded_dependencies + outcome.verification.unverified_dependencies
    assert not any(verified is True for _m, verified in checks_on(outcome, "COST")) and not outcome.release.permitted


@pytest.mark.parametrize("task_text", [
    "Is c = 3 + 2 × k the cost of a ride of k km? Find the cost of a 10 km ride.",
    "Show that c = 3 + 2 × k for a ride of k km. Find the cost of a 10 km ride.",
    "If c = 3 + 2 × k, find the cost of a 10 km ride.",
    "The rule c = 3 + 2 × k is false. Find the cost of a 10 km ride.",
    "Students often guess c = 3 + 2 × k. Find the cost of a 10 km ride.",
    "Hypothesis: c = 3 + 2 × k. Find the cost of a 10 km ride.",
    "Some say c = 3 + 2 × k. Find the cost of a 10 km ride.",
    "A ride costs $3 plus $2 per km. Find the cost of a 10 km ride.",
], ids=["question", "claim to prove", "condition", "negated", "hedged report", "hypothesis", "reported", "no formula"])
def test_a_formula_the_task_does_not_give_establishes_nothing(task_text):
    """A formula in a question, a claim to prove, a condition, a negation, a report or a hypothesis is not given by the
    task; and words that describe the rule are no formula. The relation stays the translation's own (unverified), and
    release is refused."""
    claim, report = make("The ride costs 23 dollars.", subject="Mathematics")
    outcome, _ = run(claim, report, output(ride(fare(3, 2), 23)), task=TaskRecord.of("t", "r", task_text))
    assert outcome.display_status is S.ENTAILED
    assert "COST" in outcome.verification.unverified_dependencies + outcome.verification.ungrounded_dependencies
    assert not any(verified is True for _m, verified in checks_on(outcome, "COST")) and not outcome.release.permitted


def test_a_supplied_excerpt_that_states_the_rule_establishes_it_and_one_that_does_not_does_not():
    """The excerpt path: a supplied text that gives the rule ("The rule: c = 3 + 2 × k.") establishes the premise that
    cites that formula; an excerpt of the same text that only describes the fare ("$3 plus $2 per km") is located but
    states no relation."""
    doc = "Fares: $3 plus $2 per km. The rule: c = 3 + 2 × k."
    claim, report = make("The ride costs 23 dollars.", subject="Mathematics", texts=[("doc", doc)])
    task = TaskRecord.of("t", "r", "Find the cost of a 10 km ride.")
    stated = {"kind": "supplied_text", "source_refs": [{"document_id": "doc", "excerpt": "c = 3 + 2 × k"}]}
    outcome, _ = run(claim, report, output(ride(fare(3, 2), 23, kind=stated)), task=task)
    assert ("relation_in_source", True) in checks_on(outcome, "COST") and outcome.release.permitted, outcome.release.unresolved
    described = {"kind": "supplied_text", "source_refs": [{"document_id": "doc", "excerpt": "$3 plus $2 per km"}]}
    outcome, _ = run(claim, report, output(ride(fare(3, 2), 23, kind=described)), task=task)
    assert ("verbatim_match", True) in checks_on(outcome, "COST") and ("relation_in_source", None) in checks_on(outcome, "COST")
    assert outcome.verification.unverified_dependencies == ["COST"] and not outcome.release.permitted


# =========================================================================== assignments: the comparison must be established

def count_case(op, task_text):
    p = problem([{"id": "N", "expr": cmp(op, V("n"), I(17)), "label": "the count", "grounding": {"kind": "task_setting"}}],
                {"id": "C", "expr": cmp("ge", V("n"), I(1))}, (("n", "Int", None),))
    claim, report = make("At least 1 state joined.", subject="Mathematics")
    outcome, _ = run(claim, report, output(p), task=TaskRecord.of("t", "r", task_text), review=None)
    return outcome


@pytest.mark.parametrize("op,task_text,established", [
    ("eq", "17 states joined.", True),
    ("ge", "17 states joined.", True),          # n = 17 establishes n >= 17
    ("gt", "17 states joined.", False),         # but not n > 17: an invented bound
    ("eq", "More than 17 states joined.", False),  # "more than 17" establishes no n = 17
    ("gt", "More than 17 states joined.", True),
    ("ge", "At least 17 states joined.", True),
    ("eq", "At least 17 states joined.", True),  # the bound's own value (an inclusive bound)
    ("lt", "At most 17 states joined.", False),
    ("eq", "Between 15 and 17 states joined.", False),  # one end of a range
    ("eq", "17 or 18 states joined.", False),            # one option of a disjunction
    ("eq", "Any number other than 17 joined.", False),   # excluded where it stands
], ids=lambda x: x if isinstance(x, str) else str(x))
def test_an_assignment_is_established_only_by_a_figure_stated_so_that_it_establishes_the_comparison(op, task_text, established):
    """An assignment (one symbol compared with one figure) is the symbol taking the stated figure: the figure must be
    stated so that it establishes the comparison, or the comparison is an invented bound or equality."""
    outcome = count_case(op, task_text)
    verified = [v for m, v in checks_on(outcome, "N") if m == "numeric_in_task"]
    assert verified == [True if established else False], (task_text, op, checks_on(outcome, "N"))
    [premise] = outcome.translation.problem.premises
    assert premise.grounding.verified is (True if established else False)
    if "N" in outcome.verification.premises_relied_on:  # (n < 17 does not entail the conclusion n >= 1, so nothing relies on it)
        assert ("N" in outcome.verification.ungrounded_dependencies) is (not established)


# =========================================================================== the retry check reads the same rule

def test_a_retry_cannot_earn_its_verdict_with_an_invented_relation_under_a_trusted_kind():
    """After an E110 rejection a retry may add only what the source asserts, or what a check established. The retry here
    adds the relation n = m + 9 (task_setting) beside m = 8: the task states 9 and 8, which made the invented relation
    "established" before (and the retry was accepted as ENTAILED). The relation is the translation's own now, so the
    retry earned its verdict with a premise no source asserts: AMBIGUOUS_TRANSLATION, never ENTAILED."""
    definition = problem([{"id": "D", "expr": {"op": "iff", "left": V("b"), "right": eq(V("n"), I(17))}, "label": "b holds iff n equals 17",
                           "grounding": {"kind": "specialist_inference"}}],
                         {"id": "C", "expr": V("b"), "label": "b holds"}, (("b", "Bool", None), ("n", "Int", None), ("m", "Int", None)))
    retry = json.loads(json.dumps(definition))
    retry["premises"] += [{"id": "N", "expr": eq(V("n"), {"op": "add", "args": [V("m"), I(9)]}), "grounding": {"kind": "task_setting"}},
                          {"id": "M", "expr": eq(V("m"), I(8)), "grounding": {"kind": "task_setting"}}]
    claim, report = make("n equals 17, and b holds exactly when n equals 17; so b holds.", subject="Mathematics")
    outcome, provider = run(claim, report, [output(definition), output(retry)], task=TaskRecord.of("t", "r", "The offsets are 9 and 8."), review=None)
    assert len(provider.calls) == 2 and any("E110" in d for d in provider.calls[1].prior_diagnostics)
    assert outcome.translation.status is T.AMBIGUOUS_TRANSLATION and outcome.display_status is not S.ENTAILED
    [repair] = outcome.translation.repairs
    assert not repair.supported_by_source and any(c.startswith("premise N unsupported") for c in repair.changes)
    assert any(c.startswith("premise M supported: established by a grounding check") for c in repair.changes)


# =========================================================================== the closed formula reader

# =========================================================================== located excerpts are read where they stand

SPAN_DOC = "Distance 120 km over 8 hours. Use speed = d / 8 for the average."


def grounded(expr, excerpts):
    """The grounding a premise ``expr`` gets from references to ``excerpts`` of the one supplied text ``SPAN_DOC``."""
    from epinoic_logic.translate.grounding import check_problem_grounding
    refs = [{"document_id": "doc", "excerpt": e} for e in excerpts]
    p = Problem.model_validate(problem([{"id": "P", "expr": expr, "grounding": {"kind": "supplied_text", "source_refs": refs}}],
                                       {"id": "C", "expr": eq(V("d"), R(120))}, CAR_SYMBOLS))
    checked, checks = check_problem_grounding(p, [SuppliedText(document_id="doc", text=SPAN_DOC)])
    return checked.premises[0].grounding.verified, [(c.method, c.verified) for c in checks if c.target_id == "P"]


@pytest.mark.parametrize("excerpts,verified", [
    (["Distance 120 km", "8 hours"], True),
    (["8 hours", "Distance 120 km"], True),  # the order of the references changes nothing
    (["8 hours"], False),                    # the located excerpt does not state 120
    (["Distance ... 8 hours"], False),       # the elision leaves 120 out: an elided excerpt states only what it quotes
    (["Distance 120 km ... hours"], True),
], ids=["two refs", "two refs reversed", "other figure", "elided over the figure", "elided quoting the figure"])
def test_an_assignment_is_read_in_the_located_spans_of_all_its_references(excerpts, verified):
    """The excerpt check reads a located excerpt where it stands in its document (so the words around a figure decide
    what it states). Found by the measurement of this repair: two references to one document kept only the last span, so
    d = 120 cited as "Distance 120 km" and "8 hours" was refuted in one order and verified in the other. Every located span
    counts, and an elided excerpt's span counts only the figures the excerpt itself quotes."""
    got, checks = grounded(eq(V("d"), R(120)), excerpts)
    assert got is verified, checks
    assert (("figures_in_excerpt", False) in checks) is (verified is False)


@pytest.mark.parametrize("excerpt,verified", [
    ("Use speed = d / 8 for the average.", True),
    ("Distance 120 km over 8 hours.", None),                    # the relation's figures, not the relation
    ("8 hours. Use ... for the average.", None),                # the elision leaves the formula out
    ("Distance 120 km ... speed = d / 8 for the average.", True),
    ("Distance 120 km \u2026 speed = d / 8 for the average.", True),
], ids=["states it", "figures only", "elided over the formula", "elided quoting the formula", "unicode ellipsis"])
def test_a_relation_is_verified_by_a_located_excerpt_only_when_its_quoted_words_state_it(excerpt, verified):
    """A located excerpt verifies a relation only when the formula stands inside it, as a given, and (for an elided
    excerpt) among the words it quotes; otherwise the relation is the translation's own (``verified=None``)."""
    got, checks = grounded(eq(V("speed"), OVER_8), [excerpt])
    assert got is verified, checks
    assert ("relation_in_source", verified) in checks


def test_the_formula_reader_reads_comparisons_as_terms_and_declines_what_it_cannot_read():
    """The reader evaluates nothing: it parses explicit operators only, compares sums and products in any order, and
    reads no formula where a factor could be written without its operator ("2t", "8 h"), a comparison is chained, or an
    arrow joins two clauses."""
    def key(text):
        return [f.key for f in formulas_in(text)]
    assert key("c = 3 + 2 × k.") == key("c = k * 2 + 3") != []
    assert key("v = d / 8") == key("v = 0.125 * d") != []
    for unread in ("s = 2t", "s = 2 t", "v = d / 8 h", "a = b = c", "n = 17 => b", "b <=> n = 17", "v = √d", "v = d ^ 2", "A = s²",
                   "p = 5%", "√x = 2", "|x| = 2", "f(x) = 2"):
        assert key(unread) == [], unread
    assert numeric_shape(Problem.model_validate(car(TIMES_8, {"kind": "arithmetic_fact"}, 960)).premises[1].expr) == "relation"
    assert numeric_shape(Problem.model_validate(car(TIMES_8, {"kind": "arithmetic_fact"}, 960)).premises[0].expr) == "assignment"
    premise = Problem.model_validate(ride(fare(3, 2), 23)).premises[1]
    assert relation_key(premise.expr) == formulas_in("c = 3 + 2 × k")[0].key
    assert stated_relation(premise.expr, [SourceText("task", "t", "Let c = 3 + 2 × k.")]) is not None
    assert stated_relation(premise.expr, [SourceText("task", "t", "Is c = 3 + 2 × k?")]) is None


def test_the_translation_prompt_says_a_relation_is_validated_only_by_a_record_that_states_it():
    from epinoic_logic.translate import prompts
    text = prompts.load_prompt(prompts.TRANSLATE_PROMPT_VERSION)
    for needle in ("validated only", "states that same formula as a given", "figures appearing in the task do not validate it",
                   "unverified dependency, whatever its kind"):
        assert needle in text, needle
