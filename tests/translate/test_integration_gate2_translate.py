"""Integration gate 2, the class sweep in the translation layer (translate/): the instances of the critical input stall's
class found and fixed here, each read exactly as before on ordinary text (the old reading is kept below as the
specification and compared on random texts), and one sweep test per module feeding its public text entry points the
standard hostile inputs (``tests/core_hostile.py``) under a CPU-time bound.

* ``eligibility.figure_text``: the line-start label alternative of ``_LABEL_RE`` (``(?m:^\\s*label)``) rescanned a
  whitespace run from every line start inside it (a run of n blank lines cost n² steps: 0.25 s at 4,000 line breaks,
  over 3 s at 20,000). ``_strip_labels`` reads each run once.
* ``assertion.assertion_at`` (every source a coverage check reads): ``_NO_OPENING_RE``'s ``\\n\\s*`` alternative rescanned a
  blank run from every line break (2 s at 20,000 line breaks). ``_no_openings`` reads the run before each "No" once.
* ``quantities._latex_plain``: ``_latex_group`` counted braces from every '{' to the end of the text, quadratic on unclosed
  groups (7 s on 40,000 characters of '\\frac{'). Its callers pass at most 600 characters, so this was not reachable; the
  closing brace of every '{' now comes from one pass.
"""
from __future__ import annotations

import random
import re
import time
from fractions import Fraction
from typing import Optional

import pytest

from epinoic_logic.translate import assertion as A
from epinoic_logic.translate import coverage as COV
from epinoic_logic.translate import diag_argument as DA
from epinoic_logic.translate import diag_evidence as DE
from epinoic_logic.translate import diag_figures as DF
from epinoic_logic.translate import eligibility as E
from epinoic_logic.translate import grounding as G
from epinoic_logic.translate import parsing as P
from epinoic_logic.translate import quantities as Q
from epinoic_logic.translate import review as RV
from epinoic_logic.translate import subjects as SJ
from epinoic_logic.translate.contracts import ClaimRecord, SuppliedText

from ..core_hostile import SHAPES, one, sweep


def _random_texts(pieces: list[str], n: int, seed: int, longest: int = 14):
    rng = random.Random(seed)
    for _ in range(n):
        yield "".join(rng.choice(pieces) for _ in range(rng.randint(0, longest)))


# ============================================================================================ eligibility: label lines
def test_the_labels_are_stripped_exactly_as_the_pattern_stripped_them():
    pieces = ["\n", " ", "\t", "\r", " ", "(", ")", "a", "b", "h", "i", "v", "x", "1", "12", "3", ".", "z", "\n\n", " (a) ", "1. ", "a) ", "\n  2. "]
    for text in _random_texts(pieces, 100_000, 7):
        assert E._strip_labels(text) == E._LABEL_RE.sub(" ", text), repr(text)


def test_the_figure_text_of_a_run_of_line_breaks_is_read_in_linear_time():
    c0 = time.process_time()
    for run in ("\n" * 80_000 + "x", "\n \n" * 26_000 + "1. x"):
        E.figure_text(run)
    assert time.process_time() - c0 < 3.0  # over 3 s at 20,000 line breaks before the fix


def test_decide_eligibility_on_a_claim_of_line_breaks_is_bounded():
    claim = ClaimRecord(request_id="r", task_id="t", report_id="rep", agent_id="history-specialist", subject="History", task_type="short_answer",
                        claim_id="c1", claim_text="Unemployment rose in 1930." + "\n" * 3_900 + "2.", claim_role="evidence")
    c0 = time.process_time()
    E.decide_eligibility(claim)
    assert time.process_time() - c0 < 2.0


# ============================================================================================ assertion: "No" opening a clause
def test_the_no_openings_are_read_exactly_as_the_pattern_read_them():
    pieces = ["No", "No ", " ", "\n", "\t", ".", "!", "(", ";", ":", "x", "a", "1", "$", "Nob", ",", " ", "\r", "No\n"]
    for text in _random_texts(pieces, 100_000, 11, 12):
        assert [(m.start(1), m.end(1)) for m in A._NO_OPENING_RE.finditer(text)] == A._no_openings(text), repr(text)


@pytest.mark.parametrize("run", ["\n" * 80_000 + "x", "\n \n" * 26_000 + "No 17 states joined.", "No\n" * 26_000 + "x"])
def test_a_source_of_line_breaks_is_read_for_assertions_in_linear_time(run):
    A._index.cache_clear()
    c0 = time.process_time()
    A.assertion_at(run, 0, 1)
    assert time.process_time() - c0 < 3.0  # 2 s at 20,000 line breaks before the fix


def test_a_negating_no_after_blank_lines_still_withholds_the_assertion():
    text = "The table lists the states.\n\n\nNo 17 states joined the union in 1850."
    k = text.index("17")
    reading = A.assertion_at(text, k, k + 2)
    assert not reading.asserted and reading.mood == "negation"


# ============================================================================================ quantities: LaTeX groups
def _old_latex_group(text: str, i: int) -> Optional[tuple[str, int]]:
    """The group reader before the fix (the specification): count braces from the opener."""
    n = len(text)
    while i < n and text[i] == " ":
        i += 1
    if i >= n:
        return None
    if text[i] != "{":
        return (text[i], i + 1) if text[i] not in "}\\" else None
    depth = 0
    for j in range(i, n):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
    return None


def test_the_latex_groups_are_read_exactly_as_the_brace_count_read_them():
    pieces = ["\\frac", "{", "}", "1", "x", " ", "\\times", "^", "\\sqrt", "[", "]", "\\text", "kg", "\\", "a"]
    for text in _random_texts(pieces, 60_000, 13, 16):
        closers = Q._brace_closers(text)
        for i in range(len(text) + 1):
            assert Q._latex_group(text, i, closers) == _old_latex_group(text, i), (repr(text), i)


def test_unclosed_latex_groups_are_read_in_linear_time():
    c0 = time.process_time()
    Q._latex_plain("\\frac{" * 13_000 + "x")
    Q._latex_plain("\\sqrt{" * 13_000 + "x")
    assert time.process_time() - c0 < 3.0  # 7 s on 40,000 characters of '\frac{' before the fix


# ============================================================================================ the sweep, one test per module
def _source(text: str) -> Q.SourceText:
    return Q.SourceText(kind="supplied_text", ident="src", text=text)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_assertion(shape):
    def entries(text: str):
        k = max(0, len(text) // 2)
        A._index.cache_clear()
        yield "assertion_at", lambda: A.assertion_at(text, k, k + 1)
        yield "relation_at", lambda: A.relation_at(text, k, k + 1)
        yield "stated_as", lambda: A.stated_as(text, k, k + 1, "eq")
        yield "sentence_cue_at", lambda: A.sentence_cue_at(text, k)
        yield "units_of", lambda: A.units_of(text)
        yield "content_words", lambda: A.content_words(text)
        yield "describing_units", lambda: A.describing_units([text], ["n"])
    assert not sweep(entries, texts=one(shape))


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_quantities(shape):
    def entries(text: str):
        yield "figures_in", lambda: Q.figures_in(_source(text))
        yield "is_definitional", lambda: Q.is_definitional(text)
        yield "sentence_of", lambda: Q.sentence_of(text, len(text) // 2, len(text) // 2 + 1)
        yield "in_precision_cue", lambda: Q.in_precision_cue(text, len(text) // 2)
        yield "sources_text", lambda: Q.sources_text([_source(text)])
        yield "figures and their exactness", lambda: [Q.stated_exactness(f, text) for f in Q.figures_in(_source(text))[:50]]
    assert not sweep(entries, texts=one(shape))


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_grounding(shape):
    doc = SuppliedText(document_id="d", text="In 1990 the total was 5 people.")

    def entries(text: str):
        G.clear_grounding_caches()
        hostile_doc = SuppliedText(document_id="h", text=text)
        claim = ClaimRecord(request_id="r", task_id="t", report_id="rep", agent_id="english-specialist", subject="English", task_type="short_answer",
                            claim_id="c1", claim_text=(text[:3_900] if text[:3_900].strip() else "x"), claim_role="evidence")
        yield "find_quotation(excerpt)", lambda: G.find_quotation(text[:2_000], doc.text, document_id="d")
        yield "find_quotation(text)", lambda: G.find_quotation("the total was 5", text, document_id="h")
        yield "locate_long_elision", lambda: G.locate_long_elision("In 1990 ... 5 people", text, document_id="h")
        yield "check_claim_sources", lambda: G.check_claim_sources(claim, [doc, hostile_doc])
        yield "change_clauses", lambda: G.change_clauses(text)
        yield "fold_diacritics", lambda: G.fold_diacritics(text)
        yield "unbracket_elisions", lambda: G.unbracket_elisions(text)  # integration gate 3: a leading blank run read once
    assert not sweep(entries, texts=one(shape))


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_eligibility(shape):
    def entries(text: str):
        claim = ClaimRecord(request_id="r", task_id="t", report_id="rep", agent_id="history-specialist", subject="History", task_type="short_answer",
                            claim_id="c1", claim_text=(text[:3_900] if text[:3_900].strip() else "x"), claim_role="evidence")
        yield "figure_text", lambda: E.figure_text(text)
        yield "has_numeral", lambda: E.has_numeral(text, scripts=True)
        yield "has_comparative", lambda: E.has_comparative(text)
        yield "has_relation_sign", lambda: E.has_relation_sign(text)
        yield "decide_eligibility", lambda: E.decide_eligibility(claim)
    assert not sweep(entries, texts=one(shape))


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_coverage(shape):
    def entries(text: str):
        A._index.cache_clear()
        yield "source_asserted", lambda: COV.source_asserted(Fraction(17), "the number of states", [_source(text)])
        yield "asserting_spans", lambda: COV.asserting_spans(Fraction(5), None, [_source("In 1990 the total was 5 people. " + text)])
    assert not sweep(entries, texts=one(shape))


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_parsing(shape):
    def entries(text: str):
        yield "parse_json_object", lambda: P.parse_json_object(text)
        yield "parse_json_object(strict)", lambda: P.parse_json_object(text, strict=True)
        yield "strip_code_fences", lambda: P.strip_code_fences(text)
    assert not sweep(entries, texts=one(shape))  # a text that is no JSON object is refused with a ValueError (a refusal, allowed)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_review_and_subjects(shape):
    def entries(text: str):
        yield "parse_review_output", lambda: RV.parse_review_output(text)
        yield "resolve_profile", lambda: SJ.resolve_profile(text)
    assert not sweep(entries, texts=one(shape))


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_diagnosis_readers(shape):
    def entries(text: str):
        yield "diag_argument.has_reason_connective", lambda: DA.has_reason_connective(text)
        yield "diag_argument.mask_quotations", lambda: DA.mask_quotations(text)
        yield "diag_argument.offers_cause", lambda: DA.offers_cause(text)
        yield "diag_argument.wrapped_passage", lambda: DA.wrapped_passage(text)
        yield "diag_argument.bare_yes_no", lambda: DA.bare_yes_no(text)
        yield "diag_argument.unbridged_leap_reading", lambda: DA.unbridged_leap_reading([text], "the price rose", "demand fell")
        yield "diag_evidence.asks_own_knowledge", lambda: DE.asks_own_knowledge(text)
        yield "diag_evidence.source_bound", lambda: DE.source_bound(text)
        yield "diag_figures.qualifier_years", lambda: DF.qualifier_years(text)
        yield "diag_figures.worked_results", lambda: DF.worked_results([text], [_source(text)])
    assert not sweep(entries, texts=one(shape))


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_readers_of_an_encoding_against_its_sources(shape):
    """The readers that set an IR problem against its sources (pipeline.introduced_figures, precision.read_sites,
    relations.stated_relation, stated_rules.stated_rule) on a source that carries each hostile run."""
    from epinoic_logic.ir.schema import Problem
    from epinoic_logic.translate import pipeline as PL
    from epinoic_logic.translate import precision as PR
    from epinoic_logic.translate import relations as REL
    from epinoic_logic.translate import stated_rules as SR
    problem = Problem.model_validate({
        "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": "n", "sort": "Int", "meaning": "the number of states"}, {"name": "b", "sort": "Bool", "meaning": "the union grew"}],
        "premises": [{"id": "P1", "expr": {"op": "eq", "left": {"op": "var", "name": "n"}, "right": {"op": "int", "value": "17"}}},
                     {"id": "P2", "expr": {"op": "iff", "left": {"op": "var", "name": "b"},
                                           "right": {"op": "gt", "left": {"op": "var", "name": "n"}, "right": {"op": "int", "value": "13"}}}}],
        "conclusion": {"id": "C", "expr": {"op": "var", "name": "b"}}})
    symbols = {s.name: s for s in problem.symbols}

    def entries(text: str):
        src = _source("In 1850 there were 17 states. " + text)
        yield "pipeline.introduced_figures", lambda: PL.introduced_figures(problem, [src])
        yield "precision.read_sites", lambda: PR.read_sites(problem, [src])
        yield "relations.stated_relation", lambda: REL.stated_relation(problem.premises[0].expr, [src])
        yield "stated_rules.stated_rule", lambda: SR.stated_rule(problem.premises[1].expr, symbols, src, (0, len(src.text)))
    assert not sweep(entries, texts=one(shape))
