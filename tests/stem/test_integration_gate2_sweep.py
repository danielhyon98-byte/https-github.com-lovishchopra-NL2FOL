"""Integration gate 2, the sweep for the class of the critical input stall (a regular-expression blow-up, a quadratic scan or rescan
of the text, unbounded work on oversize or nested input): one test per module of ``epinoic_logic.stem`` that feeds each of its public
entry points the standard hostile inputs (runs of about 20,000 characters of blanks, tabs, line breaks, stops, closing marks, mark
labels such as (A1), parentheses, brackets, fence openers, number words joined by 'and', '=' links and list markers, each followed by
a character that defeats the match, and the two shapes the sweep found: a compound quantity repeated and a run of masked-maths letters)
and asserts a CPU-time bound with a wide margin per call.

The instances the sweep fixed (docs/STEM_DESIGN.md, section 36): the masked-run prefix of rules inline-restatement and restated-result
(``relations._MASKED_RUN``: 'X+x*' under IGNORECASE, about 9 ms per 150-character window, 9 s on '4 minutes 30 seconds' repeated to
20,000 characters), the numeral lines of the answer proper (``hub_hooks._numeral_lines``: quadratic on a blank or tab run, 2 s at
20,000), a Markdown separator row (``datatables._SEPARATOR_RE``, 4.2 s on a blank line), the rounding phrases after a value
(``_ROUND_AFTER_RE``, ``_ROUNDED_TAIL_RE``, ``_CLAUSE_END_RE``: up to 0.9 s on 120 characters), the tail of a described value
(``_DESCRIBED_TAIL_RE``), a row's trailing adverbs (``_ROW_LEAD_ADVERBS_RE``), a comparison stated false (``_STATED_FALSE_RE``), the
time that is a number of half-lives (``_TIME_IS_RE`` and its rescan per prose value), the words naming base 2 (``_BINARY_WORD_RE``),
the scope phrase of a statement (``_LEAD_SCOPE_RE``) and a description's subordinate clause (``_DESCRIPTION_STOP_RE``).
"""
from __future__ import annotations

import time
from typing import Callable

import pytest

import importlib
from epinoic_logic.stem import (
    boolean, calculus, chem, constants, datatables, enclosures, hub_hooks, layout, lexer, models, nodes, normalize, numbers, parser, reference,
    relations, scaling, scope, si_reading, spans, to_ir, tolerance, units, word_formulas,
)
from epinoic_logic.stem import checks, document
from epinoic_logic.stem.document import build_document, clear_document_cache
from epinoic_logic.stem.limits import DEFAULT_LIMITS, profile_for

#: the module itself (the package exports the parser's ``segment`` function under the same name)
segment_module = importlib.import_module("epinoic_logic.stem.segment")

N = 20_000
#: the standard hostile inputs, each followed by a character that defeats the match
SHAPES: dict[str, str] = {
    "blanks": " " * N + "x", "tabs": "\t" * N + "x", "line breaks": "\n" * N + "x", "stops": "." * N + "x",
    "closing marks": ")" * (N // 2) + "]" * (N // 2) + "x", "mark labels": "x = 5" + " (A1)" * (N // 5) + " z",
    "parentheses": "(" * N + "x", "brackets": "[" * N + "x", "fence openers": "```\n" * (N // 4) + "x",
    "number words": "one and " * (N // 8) + "x", "= links": "x = " * (N // 4) + "!", "list markers": "- " * (N // 2) + "!",
    "compound quantities": "4 minutes 30 seconds " * (N // 21) + "!", "masked letters": "xX" * (N // 2) + ", so",
}
#: per call, CPU seconds: a direct entry point (measured at most tens of milliseconds on every shape) and a whole document (measured
#: well under one second); a quadratic scan of 20,000 characters takes seconds, a regular-expression blow-up far longer
DIRECT_BOUND = 1.0
DOCUMENT_BOUND = 8.0


def _sweep(entries: Callable[[str], list[tuple[str, Callable[[], object]]]], bound: float = DIRECT_BOUND) -> None:
    slow = []
    for shape, text in SHAPES.items():
        for name, call in entries(text):
            clear_document_cache()
            c0 = time.process_time()
            try:
                call()
            except (ValueError, OverflowError):
                pass  # a parse function refusing hostile input fails loudly, which is allowed; a stall is not
            spent = time.process_time() - c0
            if spent > bound:
                slow.append((name, shape, round(spent, 2)))
    assert not slow, slow


PHYSICS, CS = profile_for("physics"), profile_for("computer_science")


def test_sweep_normalize():
    _sweep(lambda t: [("reading_view", lambda: normalize.reading_view(t)), ("prose_view", lambda: normalize.prose_view(t, [(0, 5)], [(5, 9)])),
                      ("masked_view", lambda: normalize.masked_view(t, [(0, 5)])), ("blank_ranges", lambda: normalize.blank_ranges(t, [(0, 5)]))])


def test_sweep_spans():
    _sweep(lambda t: [("find_spans/physics", lambda: spans.find_spans(t, profile=PHYSICS)), ("find_spans/cs", lambda: spans.find_spans(t, profile=CS)),
                      ("split_lines", lambda: spans.split_lines(t))])


def test_sweep_segment():
    _sweep(lambda t: [("segment_statements", lambda: segment_module.segment_statements(t, spans.find_spans(t, profile=PHYSICS)))])


def test_sweep_layout():
    _sweep(lambda t: [("plain_line", lambda: layout.plain_line(t)), ("annotation_ranges", lambda: layout.annotation_ranges(t)),
                      ("strip_trailing_annotations", lambda: layout.strip_trailing_annotations(t)),
                      ("trailing_annotation_span", lambda: layout.trailing_annotation_span(t)), ("label_only_rest", lambda: layout.label_only_rest(t)),
                      ("is_working", lambda: layout.is_working(t)), ("joins_previous", lambda: layout.joins_previous(t, t)),
                      ("emphasis_spans", lambda: layout.emphasis_spans(t))])


def test_sweep_lexer():
    _sweep(lambda t: [("lex/plain", lambda: lexer.lex(t, 0, len(t))), ("lex/latex", lambda: lexer.lex(t, 0, len(t), mode="latex")),
                      ("lex/cs", lambda: lexer.lex(t, 0, len(t), cs=True)), ("combination_at", lambda: lexer.combination_at(t, 0, len(t)))])


def test_sweep_parser():
    _sweep(lambda t: [("parse_math", lambda: parser.parse_math(lexer.lex(t, 0, len(t)).tokens, parser.ParseContext(s=t))),
                      ("segment", lambda: parser.segment(t[:DEFAULT_LIMITS.max_letter_run * 4], frozenset({"x", "y"})))])


def test_sweep_numbers():
    _sweep(lambda t: [("scan_number", lambda: numbers.scan_number(t, 0)), ("scan_based", lambda: numbers.scan_based(t, 0)),
                      ("superscript_int", lambda: numbers.superscript_int(t, 0, len(t)))])


def test_sweep_units():
    _sweep(lambda t: [("parse_unit", lambda: units.parse_unit(t)), ("unit_dimension", lambda: units.unit_dimension(t)),
                      ("is_unit_atom", lambda: units.is_unit_atom(t)), ("english_word_atom", lambda: units.english_word_atom(t)),
                      ("lookup_atom", lambda: units.lookup_atom(t, "physics"))])


def test_sweep_chem():
    _sweep(lambda t: [("find_equations", lambda: chem.find_equations(t)), ("parse_equation", lambda: chem.parse_equation(t)),
                      ("parse_species", lambda: chem.parse_species(t)), ("latex_to_chem", lambda: chem.latex_to_chem(t)),
                      ("canonical_formula", lambda: chem.canonical_formula(t[:200]))])


def test_sweep_boolean():
    def entries(t):
        toks = lexer.lex(t, 0, len(t), cs=True).tokens
        lines = t.split("\n")
        return [("parse_expression", lambda: boolean.parse_expression(t, 0, len(t))), ("parse_boolean", lambda: boolean.parse_boolean(toks)),
                ("truth_table_shape", lambda: boolean.truth_table_shape(lines)), ("gate_order", lambda: boolean.gate_order(toks)),
                ("is_boolean_context", lambda: boolean.is_boolean_context(toks, True)),
                ("parse_truth_table", lambda: boolean.parse_truth_table("A B Q\n" + t, ((0, 5), (6, 6 + len(t))))),
                ("parse_truth_table/rows", lambda: boolean.parse_truth_table("A B | Q\n" + "0 1 | 1\n" * 30 + t, ((0, 7), (8, 8 + 240 + len(t)))))]
    _sweep(entries)


def test_sweep_datatables():
    _sweep(lambda t: [("parse_data_tables", lambda: datatables.parse_data_tables((t,))),
                      ("parse_data_tables/table", lambda: datatables.parse_data_tables(("| t / s | x / m |\n|---|---|\n| 1 | 2 |\n" + t,)))])


def test_sweep_scope():
    _sweep(lambda t: [("prescan_names", lambda: scope.prescan_names(t))])


def test_sweep_si_reading():
    _sweep(lambda t: [("mask_number_marks", lambda: si_reading.mask_number_marks(t)), ("si_number", lambda: si_reading.si_number(t)),
                      ("si_digits_pattern", lambda: si_reading.si_digits_pattern())])


def test_sweep_tolerance():
    _sweep(lambda t: [("approx_word_before", lambda: tolerance.approx_word_before(t)), ("approx_word_in", lambda: tolerance.approx_word_in(t))])


def test_sweep_relations():
    _sweep(lambda t: [("named_quantities", lambda: relations.named_quantities(t)), ("inline restatement", lambda: relations._inline_restatement(t)),
                      ("rounding cue", lambda: relations._rounding_cue(t, t, 1)), ("clause ends", lambda: relations._clause_ends(t)),
                      ("result cue", lambda: relations._result_cue(t)), ("ask sentences", lambda: list(relations._ask_sentences(t))),
                      ("prose ranges", lambda: relations._prose_ranges(t))])


def test_sweep_word_formulas():
    _sweep(lambda t: [("word_formula_view", lambda: word_formulas.word_formula_view(t, "physics"))])


def test_sweep_to_ir():
    _sweep(lambda t: [("ir_name", lambda: to_ir.ir_name(t[:200]))])


def test_sweep_reference_and_constants():
    _sweep(lambda t: [("quantities_for", lambda: reference.quantities_for(t, "physics")), ("fixed_quantity", lambda: reference.fixed_quantity(t, "physics")),
                      ("constants_for_symbol", lambda: constants.constants_for_symbol(t, "physics"))])


def test_sweep_hub_hooks():
    hooks = hub_hooks.StemHooks()
    _sweep(lambda t: [("numeral lines", lambda: hub_hooks._numeral_lines(t))])
    _sweep(lambda t: [("word_count_view", lambda: hooks.word_count_view(t, "physics")),
                      ("coverage_terms", lambda: hooks.coverage_terms(t[:2000], t, "Calculate x.", "physics")),
                      ("echo_exempt", lambda: hooks.echo_exempt(t, t, "physics"))], bound=DOCUMENT_BOUND)


def test_sweep_document_and_checks():
    _sweep(lambda t: [(f"build_document/{p}", lambda p=p: build_document(t, "Calculate x.", p))
                      for p in ("physics", "chemistry", "mathematics_aa", "computer_science")]
           + [("build_document/request", lambda: build_document("x = 2 × 3 = 6", t, "physics")),
              ("build_checks", lambda: checks.build_checks(build_document(t, "Solve x.", "mathematics_aa")))], bound=DOCUMENT_BOUND)


def test_sweep_node_modules():
    """The modules whose entry points take the parsed nodes (nodes, calculus, models, scaling, enclosures): every node the front end reads
    from each hostile input goes through them."""
    def entries(t):
        doc = build_document(t, "Calculate x.", "mathematics_aa")
        trees = [n for it in doc.items for ch in it.chains for op in ch.operands for n in op.readings][:200]

        def through_nodes():
            for n in trees:
                nodes.render(n), nodes.shape_key(n), nodes.symbols(n), nodes.is_closed(n), nodes.depth(n), nodes.node_count(n), nodes.value_of(n)

        def through_calculus_and_models():
            for n in trees:
                calculus.polynomial(n, "x"), models.exponent_polynomial(n), models.exact_value(n), models.has_exponential(n)

        return [("nodes", through_nodes), ("calculus and models", through_calculus_and_models),
                ("scaling", lambda: scaling.literal_text(scaling.split(__import__("fractions").Fraction(len(t), 7))[0])),
                ("enclosures", lambda: enclosures.enclose("sqrt", enclosures.Interval(__import__("fractions").Fraction(len(t)),
                                                                                       __import__("fractions").Fraction(len(t)))))]
    _sweep(entries, bound=DOCUMENT_BOUND)


def test_the_fixed_instances_hold_their_old_readings():
    """Behaviour unchanged on ordinary input: each rewritten pattern gives the reading it gave before the sweep (checked against the
    patterns as they were, on these inputs)."""
    assert relations._inline_restatement("Xxxxxxxx, so ") and relations._inline_restatement("Xxxx (the result), which is about ")
    assert relations._inline_restatement("the box so ")  # a letter x before the connective reads as before (no behaviour change)
    assert not relations._inline_restatement("so ")
    assert relations._ROUND_AFTER_RE.match(" euros, to the nearest euro") and relations._ROUNDED_TAIL_RE.match(" to 2 s.f.")
    assert relations._CLAUSE_END_RE.match(" (to 2 s.f.).") and relations._CLAUSE_END_RE.match(".")
    assert relations._DESCRIBED_TAIL_RE.match(" (to 2 d.p.).") and relations._TIME_IS_RE.match(", which is equal to ") is None
    assert relations._TIME_IS_RE.match(" = ") and relations._STATED_FALSE_RE.match(" which is false")
    assert relations._ROW_LEAD_ADVERBS_RE.sub("", "the rate is only") == "the rate is"
    assert relations._BINARY_WORD_RE.search("an 8-bit register") and relations._BINARY_WORD_RE.search("in binary")
    assert relations._LEAD_SCOPE_RE.match("For car P, m = 2.0 kg").group(1) == "For car P"
    assert relations._DESCRIPTION_STOP_RE.sub("", "the payment which is due") == "the payment"
    assert datatables._SEPARATOR_RE.match("|---|:--:|") and datatables._SEPARATOR_RE.match(" --- | --- ")
    assert hub_hooks._numeral_lines("Total:\n21 131.40 − 18 000.00 = 3 131.40\nend") == "Total:\n Xmath \nend"
    assert document is not None
