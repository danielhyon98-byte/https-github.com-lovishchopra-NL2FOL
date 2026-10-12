"""The single-pass lexer (docs/STEM_DESIGN.md, section 4.4)."""
from __future__ import annotations

import time
from fractions import Fraction

import pytest

from epinoic_logic.stem.lexer import lex
from epinoic_logic.stem.limits import StemLimits
from epinoic_logic.stem.normalize import reading_view


def kinds(s: str, **kw) -> list[str]:
    return [t.kind for t in lex(s, **kw).tokens]


def toks(s: str, **kw):
    return lex(s, **kw).tokens


def test_offsets_are_offsets_of_the_input():
    s = "Then v₀ = 5.0 m s⁻¹ and"
    a, b = s.index("v"), s.index(" and")
    for t in toks(s, start=a, end=b):
        assert a <= t.start < t.end <= b
        assert s[t.start:t.end] == t.text or t.kind in ("IDENT", "SUP")
    first = toks(s, start=a, end=b)[0]
    assert first.kind == "IDENT" and first.text == "v" and first.sub == "0" and first.end == a + 2


def test_space_flag_tells_juxtaposition_from_a_gap():
    ms = toks("ms")
    assert len(ms) == 1 and ms[0].text == "ms"
    m_s = toks("m s")
    assert [t.text for t in m_s] == ["m", "s"] and not m_s[0].space and m_s[1].space


def test_numbers_carry_exact_values():
    t = toks("v = 5.0 m s⁻¹")
    assert t[2].kind == "NUM" and t[2].value.value == 5 and t[2].value.sig_figs == 2
    assert t[-1].kind == "SUP" and t[-1].value == -1
    sci = toks(r"1.2 \times 10^{-3}", mode="latex")
    assert len(sci) == 1 and sci[0].kind == "NUM" and sci[0].value.value == Fraction(3, 2500)
    half = toks("½gt²")
    assert half[0].kind == "NUM" and half[0].value.value == Fraction(1, 2) and half[1].text == "gt"
    assert toks("1,000")[0].value.value == 1000
    assert [t.kind for t in toks("3.14.15")] == ["NUM", "PUNCT", "NUM"]


def test_values_false_skips_building_numbers():
    t = toks("v = 6.67e-11", values=False)
    assert t[-1].kind == "NUM" and t[-1].value is None and t[-1].text == "6.67e-11"


def test_numbers_breaking_a_bound_are_numerr_tokens():
    t = toks("x = " + "7" * 40)
    assert t[-1].kind == "NUMERR" and t[-1].value[0] == "ST-LIM-001"
    t = toks("1e500")
    assert t[0].kind == "NUMERR"


def test_subscripts_primes_and_delta():
    t = toks("Δv = v_{max} - v₀")
    assert t[0].delta and t[0].text == "v"
    assert t[2].sub == "max" and t[4].sub == "0"
    assert toks("f′(x)")[0].primes == 1 and toks("x''")[0].primes == 2
    dh = toks("ΔH°")
    assert len(dh) == 1 and dh[0].delta and dh[0].sub == "°"
    assert toks(r"\Delta H", mode="latex")[0].delta
    assert toks("T½")[0].sub == "half" and toks("W∥")[0].sub == "par" and toks("Q1")[0].sub == "1"


def test_functions():
    assert toks("sin⁻¹(0.5)")[0].text == "arcsin"
    assert toks(r"\sin^{-1} x", mode="latex")[0].text == "arcsin"
    log2 = toks("log₂ 8")[0]
    assert log2.kind == "FUNC" and log2.value == 2
    assert toks("log_{10} 100")[0].value == 10 and toks(r"\log_{2} 8", mode="latex")[0].value == 2
    assert toks("lg 100")[0].text == "log10"
    assert [t.text for t in toks("√(x) ∛8 exp(2) ln x") if t.kind == "FUNC"] == ["sqrt", "cbrt", "exp", "ln"]


@pytest.mark.parametrize("s, rel", [
    ("a <= b", "≤"), ("a >= b", "≥"), ("a != b", "≠"), ("a ~ b", "≈"), ("a => b", "⇒"), ("a ≤ b", "≤"), ("a ∴ b", "∴"), ("a → b", "→"), ("a ⇌ b", "⇌"),
])
def test_relations_have_one_spelling(s, rel):
    assert toks(s)[1].kind == "REL" and toks(s)[1].text == rel


def test_latex_relations_operators_and_groups():
    assert [t.text for t in toks(r"\leq \geq \neq \approx", mode="latex")] == ["≤", "≥", "≠", "≈"]
    assert [t.text for t in toks(r"\cdot \times \div \pm", mode="latex")] == ["·", "×", "÷", "±"]
    assert kinds(r"\frac{1}{2} m v^2", mode="latex") == ["LATEX", "LGROUP", "NUM", "RGROUP", "LGROUP", "NUM", "RGROUP", "IDENT", "IDENT", "CARET", "NUM"]
    assert kinds(r"\left( x \right)", mode="latex") == ["LPAR", "IDENT", "RPAR"]
    assert [t.text for t in toks(r"\alpha + \beta", mode="latex")] == ["α", "+", "β"]
    assert kinds(r"a & b \\ c", mode="latex") == ["IDENT", "AMP", "IDENT", "ROWSEP", "IDENT"]
    text = toks(r"v_0 = 5.0\,\text{m s}^{-1}", mode="latex")[3]
    assert text.kind == "TEXT" and text.text == "m s"


def test_tex_superscript_takes_one_character():
    assert kinds("x^23", mode="latex") == ["IDENT", "CARET", "NUM", "NUM"]      # x^23 is x²·3 in TeX
    assert kinds("x^{23}", mode="latex") == ["IDENT", "CARET", "LGROUP", "NUM", "RGROUP"]


def test_unsupported_constructs_are_named():
    for s, mode in ((r"\int_0^1 x\,dx", "latex"), (r"\sum_{i=1}^n i", "latex"), ("Σ x", "plain"), (r"\Sigma", "latex"), ("∂f", "plain"), ("∫ x dx", "plain"),
                    (r"\begin{pmatrix}", "latex")):
        first = toks(s, mode=mode)[0]
        assert first.kind == "UNSUP" and first.value, s


def test_unknown_latex_and_confusables_are_errors():
    t = toks(r"\foo{x}", mode="latex")
    assert t[0].kind == "ERROR" and "\\foo" in t[0].value
    cyr = toks("а = 3")                      # Cyrillic а
    assert cyr[0].kind == "ERROR"
    assert all(t.kind != "IDENT" for t in toks("сос"))   # Cyrillic сос
    assert toks("１")[0].kind != "NUM"          # a full-width digit is no digit


def test_boolean_words_only_in_computer_science():
    assert kinds("A AND B OR NOT C", cs=True) == ["IDENT", "BOOL", "IDENT", "BOOL", "BOOL", "IDENT"]
    assert kinds("A AND B") == ["IDENT", "IDENT", "IDENT"]
    assert toks("A XOR B", cs=True)[1].text == "⊕"


def test_based_numerals():
    assert toks("0xFF")[0].value.value == 255 and toks("0b1010")[0].value.value == 10
    assert toks("1010₂")[0].kind == "NUM" and toks("1010₂")[0].value.value == 10
    assert toks("FF₁₆", cs=True)[0].kind == "NUM"
    assert toks("FF₁₆")[0].kind == "IDENT"          # outside Computer Science FF₁₆ is a name with a subscript
    p = toks("(255)₁₀")
    assert [t.kind for t in p] == ["LPAR", "NUM", "RPAR", "SUB"] and p[-1].value == "10"


def test_other_tokens():
    assert kinds("25 °C 50%") == ["NUM", "DEGREE", "NUM", "PERCENT"]
    assert kinds("5! a | b") == ["NUM", "BANG", "IDENT", "BAR", "IDENT"]
    assert kinds("x ** 2") == ["IDENT", "DSTAR", "NUM"]
    assert kinds("3–5 s") == ["NUM", "OTHER", "NUM", "IDENT"]   # a range dash is no minus
    assert kinds("∞ ✓ ? …") == ["INF", "OTHER", "PUNCT", "PUNCT"]
    assert kinds(reading_view("x − 3")) == ["IDENT", "OP", "NUM"]


def test_nested_power_of_ten_is_right_associative():
    t = toks("10^10^10")
    assert [k.kind for k in t] == ["NUM", "CARET", "NUM"]
    assert t[0].value.value == 10 and t[2].value.value == 10 ** 10   # 10^(10^10): the parser refuses the power


def test_token_bound_sets_overflow():
    lim = StemLimits(max_tokens_per_span=50)
    r = lex("x + " * 1000, limits=lim, max_tokens=lim.max_tokens_per_span)   # the caller passes the span bound
    assert r.overflow and len(r.tokens) == 50
    r = lex("x + 1", max_tokens=2)
    assert r.overflow and len(r.tokens) == 2
    r = lex("x + 1   ", max_tokens=3)                # exactly at the cap with only trailing space: no overflow
    assert not r.overflow and len(r.tokens) == 3
    assert not lex("x + " * 1000).overflow                  # no cap unless one is passed


@pytest.mark.parametrize("s, mode", [
    (r"\frac{1}{", "latex"), (r"\frac{{{{{{", "latex"), ("\\", "latex"), (r"\text{unclosed", "latex"), ("^^^^", "plain"), ("_{", "plain"), ("x_", "plain"),
    ("((((((((", "plain"), ("1e", "plain"), ("1e-", "plain"), ("0x", "plain"), ("́́", "plain"), ("퟿\U0010ffff", "plain"), ("", "plain"),
    (r"\left", "latex"), (r"\sqrt[", "latex"), ("log_", "plain"), ("sin⁻", "plain"), ("10^{", "plain"), ("1.2 × 10^", "plain"),
])
def test_malformed_input_never_raises(s, mode):
    r = lex(s, mode=mode)
    for t in r.tokens:
        assert 0 <= t.start <= t.end <= len(s)


def test_lexing_is_linear():
    s = ("v₀ = 5.0 m s⁻¹, Δx = ½at² + 1.2 × 10⁻³ ; " * 2000)
    t = time.perf_counter()
    r = lex(s, max_tokens=10 ** 6)
    assert not r.overflow and len(r.tokens) > 20000
    assert time.perf_counter() - t < 2.0
    t = time.perf_counter()
    lex("{" * 20000 + "}" * 20000, mode="latex", max_tokens=10 ** 6)
    lex("\\" * 40000, mode="latex", max_tokens=10 ** 6)
    lex("1e" * 20000, max_tokens=10 ** 6)
    assert time.perf_counter() - t < 2.0
