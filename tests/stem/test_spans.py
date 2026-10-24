"""Span extraction (docs/STEM_DESIGN.md, section 4.2)."""
from __future__ import annotations

import time

import pytest

from epinoic_logic.stem.limits import PROFILES, StemLimits
from epinoic_logic.stem.spans import find_spans, split_lines


def spans(text: str, profile: str = "physics", **kw):
    return find_spans(text, profile=PROFILES[profile], **kw)


def kinds_texts(text: str, profile: str = "physics", **kw) -> list[tuple[str, str]]:
    return [(s.kind, text[s.start:s.end]) for s in spans(text, profile, **kw).spans]


# ---------------------------------------------------------------- code

def test_code_fences_inline_and_unclosed():
    text = "```python\nx = 1\nprint(x)\n```\nThen v = 5 m s⁻¹."
    ss = spans(text)
    assert [(s.kind, s.lang) for s in ss.spans] == [("code_block", "python"), ("math_run", "")]
    assert kinds_texts("Use `a = 2` here and v = 3.") == [("code_inline", "`a = 2`"), ("math_run", "v = 3")]
    assert kinds_texts("```\nunclosed fence\nx = 2") == [("code_block", "```\nunclosed fence\nx = 2")]   # runs to the end
    assert kinds_texts("~~~\ny = 1\n~~~") == [("code_block", "~~~\ny = 1\n~~~")]


def test_indented_code_only_in_computer_science():
    assert kinds_texts("    x = 1\n    y = 2\nText.", "computer_science") == [("code_block", "    x = 1\n    y = 2")]
    assert kinds_texts("    x = 1\nText.") == [("math_run", "x = 1")]


# ---------------------------------------------------------------- LaTeX

def test_display_rows_and_environments():
    text = "$$\nv = u + at \\\\\n= 0 + 2 \\times 3\n$$"
    sp = spans(text).spans[0]
    assert sp.kind == "latex_display" and sp.mode == "latex"
    assert [text[a:b].strip() for a, b in sp.rows] == ["v = u + at", "= 0 + 2 \\times 3"]
    text = "\\begin{align*}\nx &= 2 \\\\\ny &= 3\n\\end{align*}"
    assert [text[a:b].strip() for a, b in spans(text).spans[0].rows] == ["x &= 2", "y &= 3"]
    text = "$$\\begin{aligned} a &= 1 \\\\ b &= 2 \\end{aligned}$$"
    assert [text[a:b].strip() for a, b in spans(text).spans[0].rows] == ["a &= 1", "b &= 2"]   # the inner wrapper is read through
    assert kinds_texts("\\[ E = mc^2 \\]") == [("latex_display", "\\[ E = mc^2 \\]")]


def test_inline_latex_under_the_tex_rule():
    assert kinds_texts("The value $x = 3$ and \\(y = 4\\).") == [("latex_inline", "$x = 3$"), ("latex_inline", "\\(y = 4\\)")]
    assert kinds_texts("It costs $5 per kg and $10 per bag.") == []         # currency
    assert kinds_texts("Price $5$0 is odd.") == []                           # followed by a digit
    assert ("latex_inline", "$ x = 3$") not in kinds_texts("Cost \\$5 and $ x = 3$ here.")   # leading space: no inline math
    assert kinds_texts("A $x = 1\n\ny = 2$ split.") == [("math_run", "x = 1"), ("math_run", "y = 2")]   # no inline span across a paragraph


def test_unclosed_and_malformed_latex_never_raise():
    for text in ("$$ x = 1", "\\[ x = 1", "\\begin{align} x = 1", "$\\frac{1}{$", "\\end{align}", "$$$$", "$" * 999, "\\(" * 500, "{" * 1000 + "$x$"):
        ss = spans(text)
        for s in ss.spans:
            assert 0 <= s.start <= s.end <= len(text)


def test_long_inline_span_is_not_inline_math():
    body = "x + " * 600 + "x = 1"
    out = kinds_texts("$" + body + "$")
    assert ("latex_inline", "$" + body + "$") not in out


# ---------------------------------------------------------------- chemistry

def test_chemical_equations_only_in_chemistry_profiles():
    text = "CaCO₃ → CaO + CO₂ and then 2H₂ + O₂ → 2H₂O."
    assert kinds_texts(text, "chemistry") == [("chem", "CaCO₃ → CaO + CO₂"), ("chem", "2H₂ + O₂ → 2H₂O")]
    assert [k for k, _ in kinds_texts("CaCO₃ → CaO + CO₂", "physics")] == ["math_run"]


# ---------------------------------------------------------------- prose runs

@pytest.mark.parametrize("text, expected", [
    ("The speed is v = d/t = 100/9.58 = 10.4 m s⁻¹ approximately.", ["v = d/t = 100/9.58 = 10.4 m s⁻¹"]),
    ("x = 2, y = 3, so z = 6.", ["x = 2", "y = 3", "z = 6"]),
    ("If x > 2 then y ≤ 5.", ["x > 2", "y ≤ 5"]),
    ("(x = 2)", ["x = 2"]),
    ("((x = 2))", ["x = 2"]),
    ("(since v = 0)", ["v = 0"]),
    ("so (2 × 3 = 6) ok", ["2 × 3 = 6"]),
    ("f(x) = 2 (for x > 0)", ["f(x) = 2", "x > 0"]),
    ("helium-4 has mass 4.0 u, and x = 4.", ["4.0 u", "x = 4"]),
    ("Then pV = nRT holds.", ["pV = nRT"]),
    ("∫₀¹ x dx = 1/2", ["∫₀¹ x dx = 1/2"]),
])
def test_math_runs_in_prose(text, expected):
    assert [t for _, t in kinds_texts(text, "mathematics_aa" if "∫" in text or "f(x)" in text else "physics")] == expected


def test_label_and_continuation_leads():
    sp = spans("Energy absorbed = 4.18 × 50.0 × 6.5 = 1358.5 J").spans[0]
    assert sp.lead and sp.label == "Energy absorbed"
    ss = spans("= 2.0 × 3.0\n= 6.0")
    assert [s.lead for s in ss.spans] == [True, True] and all(s.label == "" for s in ss.spans)


def test_quantities_and_asides():
    assert kinds_texts("The mass of 2.0 kg was used.") == [("quantity", "2.0 kg")]
    out = kinds_texts("A 100.0 cm³ sample (100.0 cm³ × 1.00 g cm⁻³ = 100.0 g) was heated.", "chemistry")
    assert out == [("quantity", "100.0 cm³"), ("math_run", "100.0 cm³ × 1.00 g cm⁻³ = 100.0 g")]
    assert kinds_texts("m = 100.0 g (100.0 cm³ × 1.00 g cm⁻³)")[0] == ("math_run", "m = 100.0 g")   # an aside after a unit ends the run


def test_verbal_arithmetic():
    out = kinds_texts("3 plus 4 equals 7, and 10 divided by 2 is 5.")
    assert out[0] == ("verbal", "3 plus 4 equals 7")
    sp = spans("3 plus 4 equals 7").spans[0]
    assert [t.text for t in sp.tokens] == ["3", "+", "4", "=", "7"]
    assert kinds_texts("Three plus four equals seven.") == []     # numbers only


def test_tables_and_data_lines():
    assert kinds_texts("| x | y |\n|---|---|\n| 1 | 2 |\n\nThen z = 3.") == [("table", "| x | y |\n|---|---|\n| 1 | 2 |"), ("math_run", "z = 3")]
    assert kinds_texts("[1, 2, 3]\n{2, 3}", "mathematics_aa") == [("data_line", "[1, 2, 3]"), ("data_line", "{2, 3}")]


def test_part_labels_and_markup():
    ss = spans("(a) v = 3\n(b)(ii) x = 2\nPart (c) y = 1\nQuestion 2: z = 4")
    assert [p.text for p in ss.part_labels] == ["(a)", "(b)(ii)", "Part (c)", "Question 2"]
    assert [s.kind for s in ss.spans] == ["math_run"] * 4
    ss = spans("# Heading = 3\n> quote x = 2\n- item y = 1\n1. step z = 5\n**bold** a = 1")
    assert [p.heading for p in ss.part_labels] == [True]
    text = "# Heading = 3\n> quote x = 2\n- item y = 1\n1. step z = 5\n**bold** a = 1"
    assert [text[s.start:s.end] for s in ss.spans] == ["x = 2", "y = 1", "z = 5", "a = 1"]   # no math inside a heading
    assert len(ss.math_view) == len(text) and "**" not in ss.math_view


def test_bond_label_in_chemistry():
    sp = spans("H–H bond energy = 436 kJ mol⁻¹", "chemistry").spans[0]
    assert sp.kind == "math_run" and sp.lead and sp.label == "H–H bond energy"
    assert spans("C=O bond enthalpy = 745 kJ mol⁻¹", "chemistry").spans[0].label == "C=O bond enthalpy"


def test_split_lines():
    lines = split_lines("a\nbc\n\nd")
    assert [(ln.start, ln.end, ln.index) for ln in lines] == [(0, 1, 0), (2, 4, 1), (5, 5, 2), (6, 7, 3)]


def test_span_bound_marks_long_runs():
    text = "x = " + " + ".join(["1"] * 800)
    sp = spans(text).spans[0]
    assert sp.code == "ST-LIM-001" and "span bound" in sp.error
    sp = spans("x = 1 + 2", limits=StemLimits(max_span_chars=5)).spans[0]
    assert sp.code == "ST-LIM-001"


@pytest.mark.parametrize("text", [
    "(" * 5000 + "x = 1", ")" * 5000, "x = " + "(" * 3000 + "1" + ")" * 3000, "$" * 20000, "1e" * 10000 + " = 3", "= " * 10000, "| " * 10000 + "x = 1",
    "a = " * 5000, ("word " * 4000) + "x = 1", "\\[" * 3000, "```" * 3000, "\u0430 = 3 " * 3000, "x = 1\n" * 10000,
], ids=lambda t: f"{t[:6]!r}x{len(t)}")
def test_adversarial_inputs_are_linear(text):
    t = time.perf_counter()
    ss = spans(text)
    assert time.perf_counter() - t < 2.0
    for s in ss.spans:
        assert 0 <= s.start <= s.end <= len(text)
