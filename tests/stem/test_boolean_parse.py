"""Boolean expressions and truth tables (docs/STEM_DESIGN.md, section 4.8)."""
from __future__ import annotations

import time

import pytest

from epinoic_logic.stem.boolean import is_boolean_context, parse_boolean, parse_truth_table, truth_table_shape
from epinoic_logic.stem.lexer import lex
from epinoic_logic.stem.limits import StemLimits
from epinoic_logic.stem.nodes import BoolOp, render


def B(text: str, *, mode: str = "plain", cs: bool = True, limits: StemLimits = StemLimits()):
    toks = lex(text, mode=mode, cs=cs).tokens
    rels, issues = parse_boolean(toks, limits=limits)
    return is_boolean_context(toks, cs), [(render(r.left), r.op, render(r.right)) for r in rels], [i.code for i in issues]


def table(text: str, **kw):
    lines = text.split("\n")
    rows, off = [], 0
    for ln in lines:
        rows.append((off, off + len(ln)))
        off += len(ln) + 1
    return parse_truth_table(text, tuple(rows), **kw)


@pytest.mark.parametrize("text, left, op, right", [
    ("A AND B = B AND A", "(A ∧ B)", "=", "(B ∧ A)"),
    ("A ∧ (B ∨ C) = (A ∧ B) ∨ (A ∧ C)", "(A ∧ (B ∨ C))", "=", "((A ∧ B) ∨ (A ∧ C))"),
    ("(A + B)' = A'B'", "¬((A ∨ B))", "=", "(¬(A) ∧ ¬(B))"),
    ("NOT (A OR B) = NOT A AND NOT B", "¬((A ∨ B))", "=", "(¬(A) ∧ ¬(B))"),
    ("A ⊕ B ≡ (A ∧ ¬B) ∨ (¬A ∧ B)", "(A ⊕ B)", "≡", "((A ∧ ¬(B)) ∨ (¬(A) ∧ B))"),
    ("A + 0 = A", "(A ∨ 0)", "=", "A"),
    ("A · 1 = A", "(A ∧ 1)", "=", "A"),
    ("AB + C = 1", "((A ∧ B) ∨ C)", "=", "1"),
    ("A ⇔ B", "A", "⇔", "B"),
])
def test_boolean_relations(text, left, op, right):
    ctx, rels, issues = B(text)
    assert ctx and rels == [(left, op, right)] and issues == []


def test_precedence_not_and_xor_or():
    _ctx, rels, _ = B("A OR B AND NOT C XOR D = A")
    assert rels[0][0] == "(A ∨ ((B ∧ ¬(C)) ⊕ D))"


def test_overline_in_latex():
    assert B(r"\overline{A \cdot B} = \overline{A} + \overline{B}", mode="latex")[1] == [("¬((A ∧ B))", "=", "(¬(A) ∨ ¬(B))")]


def test_boolean_context_is_computer_science_only():
    assert B("A + B = B + A")[0] is True                      # single capitals, 0/1 and + · *: Boolean in Computer Science
    assert B("A + B = B + A", cs=False)[0] is False
    assert B("x + y = 2")[0] is False and B("A + 2 = B")[0] is False and B("A^2 = B")[0] is False
    toks = lex("A ∧ B = B ∧ A").tokens
    assert is_boolean_context(toks, True) and not is_boolean_context(toks, False)


def test_errors_and_bounds_never_raise():
    assert B("x + y = 2")[2] == ["ST-PARSE-001"]
    # Rewritten to a stricter rule (repair round 2): a chain of equivalences is no longer refused as a whole; each pair of
    # neighbouring expressions is one relation the engine checks (an evaluation chain 'NOT (A AND B) = NOT (1 AND 0) = 1'
    # is checked link by link), and only a chain beyond the link bound, or an expression outside the grammar, is refused.
    assert B("A = B = C")[1:] == ([("A", "=", "B"), ("B", "=", "C")], [])
    assert B(" = ".join(["A"] * 18))[2] == ["ST-PARSE-001"]
    assert B("A = (B ∧ = C")[2] == ["ST-PARSE-001"]
    assert B("A ∧ " * 300 + "A = A")[2] == ["ST-LIM-001"]
    for text in ("A ∧", "(A ∧ B", "¬", "= A", "A ∧ = B", "((((((((((((((((((((((((((((A))))))))))))))))))))))))))) = A", "¬" * 300 + "A = A", ")" * 50):
        _ctx, rels, issues = B(text)
        assert isinstance(rels, list) and isinstance(issues, list)
    deep = "(" * 30 + "A" + ")" * 30 + " = A"
    assert B(deep)[2] == ["ST-PARSE-001"]


def test_truth_tables():
    tt = table("| A | B | A AND B |\n|---|---|---|\n| 0 | 0 | 0 |\n| 0 | 1 | 0 |\n| 1 | 0 | 0 |\n| 1 | 1 | 1 |")
    assert tt.inputs == ("A", "B") and [n for n, _ in tt.outputs] == ["A AND B"] and isinstance(tt.outputs[0][1], BoolOp)
    assert tt.rows[-1] == (True, True, True) and not tt.error
    tt = table("| A | B | A OR B |\n|---|---|---|\n| F | F | F |\n| T | F | T |")
    assert tt.rows == ((False, False, False), (True, False, True))
    assert table("| A | B | A AND B |\n|---|---|---|\n| 0 | 0 | ? |") is None            # not a truth table: a table claim
    assert table("| Name | Value |\n|---|---|\n| x | 2 |") is None


def test_truth_table_bounds():
    header = "| A | B | C | D | E | F | X |"
    tt = table(header + "\n|---|---|---|---|---|---|---|\n| 0 | 0 | 0 | 0 | 0 | 0 | 0 |")
    assert tt.code == "ST-UNDEC-001" and "7 inputs" in tt.error
    rows = "\n".join("| 0 | 1 | 1 |" for _ in range(20))
    tt = table("| A | B | A XOR B |\n|---|---|---|\n" + rows)
    assert tt.code == "ST-UNDEC-001" and "more rows" in tt.error
    tt = table("| A | B | A ? B |\n|---|---|---|\n| 0 | 0 | 0 |")
    assert tt.code == "ST-UNDEC-001" and "not a Boolean expression" in tt.error
    assert truth_table_shape(["| A | B |"]) is False


def test_boolean_is_linear():
    t = time.perf_counter()
    text = " ∨ ".join(["(A ∧ B)"] * 60) + " = A"
    for _ in range(50):
        B(text)
    assert time.perf_counter() - t < 2.0
