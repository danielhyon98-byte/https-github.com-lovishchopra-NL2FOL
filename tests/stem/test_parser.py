"""The bounded Pratt parser and the AST helpers (docs/STEM_DESIGN.md, sections 4.5 and 4.6)."""
from __future__ import annotations

import time
from fractions import Fraction

import pytest

from epinoic_logic.stem.lexer import lex
from epinoic_logic.stem.limits import PROFILES, StemLimits
from epinoic_logic.stem.nodes import (
    Abs, BinOp, Func, Magnification, Neg, Num, Percent, PlusMinus, Pow, Quantity, Ratio, Root, Sym, WithUnit, align, depth, is_closed, is_value,
    node_count, render, shape_key, symbols, unsupported_reasons, value_of, walk,
)
from epinoic_logic.stem.normalize import reading_view
from epinoic_logic.stem.parser import ParseContext, parse_math, segment, symbol_name
from epinoic_logic.stem.units import parse_unit


def P(text: str, *, mode: str = "plain", names=(), profile: str = "physics", label=None, limits: StemLimits = StemLimits()):
    rv = reading_view(text)
    toks = lex(rv, mode=mode, cs=PROFILES[profile].computer_science, limits=limits).tokens
    return parse_math(toks, ParseContext(s=rv, names=frozenset(names), profile=PROFILES[profile], limits=limits, mode=mode, lead_label=label))


def R(text: str, **kw) -> list[list[str]]:
    """Renderings: per chain, per operand, the readings joined by ' | ' (or the error code)."""
    out = []
    for ch in P(text, **kw).chains:
        out.append([" | ".join(render(r) for r in o.readings) if o.readings else o.code for o in ch.operands])
    return out


def node(text: str, **kw):
    pm = P(text, **kw)
    assert pm.chains and pm.chains[0].operands[0].readings, (text, pm.issues)
    return pm.chains[-1].operands[-1].node


# ---------------------------------------------------------------- chains and connectives

def test_chain_of_relations():
    pm = P("F = ma = 2.0 kg × 3.0 m s⁻² = 6.0 N")
    ch = pm.chains[0]
    assert ch.ops == ("=", "=", "=") and len(ch.operands) == 4 and not pm.issues
    assert render(ch.operands[1].node) == "m·a"
    q = ch.operands[2].node
    assert isinstance(q, BinOp) and isinstance(q.left, Quantity) and q.left.unit.text == "kg"


def test_connectives_split_chains():
    pm = P("2x + 3 = 11 ⇒ 2x = 8 ⇒ x = 4")
    assert [c.connective for c in pm.chains] == ["", "⇒", "⇒"]
    assert R("x = 2 or x = 3") == [["x", "2"], ["x", "3"]]
    assert [c.connective for c in P("x = 2 or x = 3").chains] == ["", "or"]
    assert [c.connective for c in P(r"x = 2 \text{ or } x = 3", mode="latex").chains] == ["", "or"]
    assert [c.connective for c in P(r"x = 2 \quad or \quad x = 3", mode="latex").chains] == ["", "or"]
    assert R("so = 3", names={"so"}) == [["so", "3"]]       # a declared name is no connective
    assert [c.connective for c in P("a = 1, b = 2; c = 3").chains] == ["", ",", ";"]


def test_continuation_and_label_leads():
    ch = P("= (2.35 − 2.50)/2.50 × 100").chains[0]
    assert ch.lead == "continuation" and ch.operands[0].node.kind == "continuation"
    ch = P("= 4.18 × 50.0 × 6.5", label="Energy absorbed").chains[0]
    assert ch.lead == "label" and ch.operands[0].node == Sym("Energy absorbed", kind="label", start=0, end=0)


def test_chain_link_bound():
    pm = P(" = ".join("abcdefghjklmnopqrstu"))
    assert pm.chains[0].links == 12 and pm.chains[0].truncated
    assert any(i.code == "ST-LIM-001" and "12 links" in i.message for i in pm.issues)


# ---------------------------------------------------------------- implicit multiplication against scope

def test_segment_by_longest_name_in_scope():
    assert segment("mgh", frozenset()) == [("m", "g", "h")]
    assert segment("PV", frozenset({"P", "V"})) == [("P", "V")]
    assert segment("GPP", frozenset()) == [("GPP",)]               # an all-capital run of three or four letters is one name
    assert segment("KE", frozenset({"KE"})) == [("KE",)]
    assert segment("xyz", frozenset({"xy", "yz"})) == [("x", "y", "z")]          # no segmentation over names: single letters
    assert len(segment("xyz", frozenset({"xy", "yz", "x", "y", "z"}))) == 3   # xy·z, x·yz, x·y·z: more than the bound


def test_two_readings_are_kept_and_more_are_refused():
    op = P("E = mgh", names={"mg", "m", "g", "h"}).chains[0].operands[1]
    assert [render(r) for r in op.readings] == ["mg·h", "m·g·h"]
    pm = P("xyz = 3", names={"xy", "yz", "x", "y", "z"})
    assert pm.chains[0].operands[0].code == "ST-PARSE-002" and pm.issues[0].code == "ST-PARSE-002"


def test_stem_names_and_symbol_names():
    assert R("KE = ½mv²") == [["KE", "½·m·v^2"]]
    assert R("s = ½gt²") == [["s", "½·g·t^2"]]           # the power binds to the last letter
    assert R("2πr") == [["2·π·r"]]
    names = [symbols(o.node) for c in P("v₀ = 1, ΔT = 3, v_{max} = 2, T½ = 3, f′ = 2").chains for o in c.operands[:1]]
    assert names == [("v_0",), ("ΔT",), ("v_max",), ("T_half",), ("f'",)]
    assert symbol_name("v", "0") == "v_0" and symbol_name("T", delta=True) == "ΔT" and symbol_name("f", primes=2) == "f''"


def test_long_lowercase_words_are_words_and_long_runs_one_symbol():
    assert R("abcdefghijklmnopq = 3") == [["abcdefghijklmnopq", "3"]]
    w = node("actual")
    assert isinstance(w, Sym) and w.kind == "word"


# ---------------------------------------------------------------- units

def test_units_after_numbers():
    assert R("m = 2.0 kg") == [["m", "2.0 [kg]"]]          # m a symbol, kg a unit
    assert isinstance(node("1.5kg"), Quantity)             # a common glued unit
    assert R("2as") == [["2·a·s"]]                          # no glued attoseconds
    q = node("v = 3.0 ms⁻¹")
    assert isinstance(q, Quantity) and len(q.unit.readings) == 2 and q.unit.ambiguity_code == "ST-UNIT-002"
    assert R("ΔT = 25 °C") == [["ΔT", "25 [°C]"]]
    w = node("(40 − 20) K")
    assert isinstance(w, WithUnit) and w.unit.text == "K"
    f = node(r"\frac{1.0}{2.0}\,\text{m s}^{-1}", mode="latex")
    assert isinstance(f, WithUnit) and f.unit.text == r"\text{m s}^{-1}" and f.unit.readings[0].dim == parse_unit("m s⁻¹").readings[0].dim
    c = node("c = 3.00 × 10⁸ M")
    assert isinstance(c, Quantity) and render(c) == "3.00 × 10⁸ [M]"
    assert len(c.unit.readings) == 2                         # bare M in physics: molar or mega
    assert len(node("c = 3.00 M", profile="chemistry").unit.readings) == 1


# ---------------------------------------------------------------- operators, powers, functions

def test_precedence_and_associativity():
    n = node("x = 2 + 3 × 4")
    assert isinstance(n, BinOp) and n.op == "+" and isinstance(n.right, BinOp) and n.right.op == "*"
    n = node("x = 8 / 4 / 2")
    assert render(n.left) == "8 / 4" and n.op == "/"
    n = node("x = -3^2")
    assert isinstance(n, Neg) and isinstance(n.arg, Pow)              # the power binds tighter than the sign
    pm = node("x = (5 ± √1)/2")
    assert isinstance(pm.left, PlusMinus) and isinstance(pm.left.right, Root) and pm.left.right.index == 2


def test_frac_and_roots():
    n = node(r"\frac{1}{2} m v^2", mode="latex")
    assert isinstance(n, BinOp) and isinstance(n.left, BinOp) and render(n.left.left) == "1 / 2" and isinstance(n.right, Pow)
    assert R(r"\sqrt{16} = 4", mode="latex") == [["sqrt(16)", "4"]]
    assert R("√16 = 4") == [["sqrt(16)", "4"]]
    assert node("x^½") == Root(Sym("x", start=0, end=1), 2, 0, node("x^½").end)
    assert isinstance(node(r"x^{1/2}", mode="latex"), Root)
    assert unsupported_reasons(node("∛8")) == ("a cube root",)


@pytest.mark.parametrize("text, exp", [("x = 2^-3", -3), ("x = 2^(-3)", -3), ("x = 2⁻³", -3), ("x = 2**3", 3), ("x^12", 12), ("e^2", 2)])
def test_integer_powers(text, exp):
    n = node(text)
    assert isinstance(n, Pow) and n.exp == exp


@pytest.mark.parametrize("text, reason", [
    ("x^13", "an integer power beyond 12 (13)"), ("x^n", "a symbolic power"), ("e^x", "a symbolic power"), ("2^(2^3)", "a fractional power"),
    ("10^10^10", "an integer power beyond 12 (10000000000)"), ("5!", "a factorial (!)"), ("lim x", "a limit"), ("∫ x dx", "an integral"),
    ("Σ x", "a sum (Σ)"), ("f′(x)", "a derivative"), ("∞", "infinity"), ("(x, y)", "a coordinate pair, vector or list"),
    ("[x²]₀²", "the evaluation of an antiderivative between limits"), ("(x)₀", "a subscript on a bracketed expression"),
])
def test_unsupported_constructs_are_nodes_with_reasons(text, reason):
    pm = P(text)
    n = pm.chains[0].operands[0].node
    assert n is not None and reason in unsupported_reasons(n), (text, n)
    assert not any(i.code.startswith("ST-PARSE") for i in pm.issues)


def test_unsupported_in_latex_and_other_constructs():
    first = P(r"\frac{dy}{dx} = 2x", mode="latex").chains[0].operands[0].node
    assert unsupported_reasons(first) == ("a derivative",)
    z = node("z = 3 + 2i")
    assert "a complex number" in unsupported_reasons(z)
    o = node("O(n²)", profile="computer_science")
    assert unsupported_reasons(o) == ("asymptotic notation",)


def test_functions_and_postfix():
    n = node("sin 30° = 0.5".split(" = ")[0])
    assert isinstance(n, Func) and n.name == "sin"
    assert R("log₂ 8 = 3") == [["log_2(8)", "3"]]
    assert R("ln(e) = 1") == [["ln(e)", "1"]]
    assert isinstance(node("50%"), Percent)
    assert isinstance(node("|x − 3|"), Abs)
    assert isinstance(node("3 : 4"), Ratio)
    m = node("× 40 = 50×".split(" = ")[1])
    assert isinstance(m, Magnification)
    assert R("f(x) = 3x² + 2") == [["f(x)", "3·x^2 + 2"]]


def test_based_numerals_in_brackets():
    n = node("(255)₁₀")
    assert isinstance(n, Num) and n.number.value == 255 and n.number.based and n.number.half_width == 0
    n = node("(1010)₂")
    assert n.number.value == 10 and n.number.base == 2        # the digits are read again in the stated base
    pm = P("(255)₂")
    assert pm.chains[0].operands[0].code == "ST-PARSE-001" and "base 2" in pm.issues[0].message
    assert P("(3.5)₁₀").chains[0].operands[0].code == "ST-PARSE-001"


# ---------------------------------------------------------------- chemistry readings

def test_chemistry_labels_bonds_and_tallies():
    assert R("n(H₂O) = 0.50 mol", profile="chemistry") == [["n(H₂O)", "0.50 [mol]"]]
    assert R("[H⁺] = 1.0 × 10⁻³ mol dm⁻³", profile="chemistry") == [["[H⁺]", "1.0 × 10⁻³ [mol dm⁻³]"]]
    assert R("pH = −log[H⁺] = 3.00", profile="chemistry") == [["pH", "-log([H⁺])", "3.00"]]
    bond = node("O=O", profile="chemistry")
    assert isinstance(bond, Sym) and bond.kind == "bond"
    assert R("C 3 = 3", profile="chemistry") == [["3", "3"]]       # an element tally label is no factor


# ---------------------------------------------------------------- errors and bounds

@pytest.mark.parametrize("text, mode, code", [
    ("x = 1 + (", "plain", "ST-PARSE-001"), ("x = )", "plain", "ST-PARSE-001"), ("x = (1 + 2]", "plain", "ST-PARSE-001"), ("|x", "plain", "ST-PARSE-001"),
    (r"\frac{\frac{\frac{1}{2}}{3}}{", "latex", "ST-PARSE-001"), (r"\sqrt{", "latex", "ST-PARSE-001"), (r"\frac", "latex", "ST-PARSE-001"),
    ("x = 1e1e1e", "plain", "ST-PARSE-001"), ("= = =", "plain", "ST-PARSE-001"),
])
def test_malformed_input_is_an_operand_error_never_an_exception(text, mode, code):
    pm = P(text, mode=mode)
    assert any(i.code == code for i in pm.issues)


def test_unknown_latex_or_confusable_makes_the_span_unparsed():
    pm = P(r"x = \foo{y}", mode="latex")
    assert pm.unparsed and pm.issues[0].code == "ST-PARSE-001" and "\\foo" in pm.issues[0].message
    pm = P("а = 3")
    assert pm.unparsed and not pm.chains


def test_nesting_depth_500_is_refused_quickly():
    for text in ("x = " + "(" * 500 + "1" + ")" * 500, "x = " + "-" * 500 + "1", r"x = " + r"\frac{" * 500 + "1" + "}{2}" * 500, "x = " + "√" * 500 + "2"):
        t = time.perf_counter()
        pm = P(text, mode="latex" if "\\" in text else "plain", limits=StemLimits(max_tokens_per_span=5000))
        assert time.perf_counter() - t < 1.0
        assert any(i.code == "ST-LIM-001" for i in pm.issues), text[:20]


def test_node_and_token_bounds():
    pm = P("x = " + "+".join(["a"] * 300))
    assert pm.unparsed and pm.issues[0].code == "ST-LIM-001"
    pm = P("x = " + "+".join(["a"] * 150), limits=StemLimits(max_ast_nodes=100))
    assert pm.chains[0].operands[1].code == "ST-LIM-001"
    pm = P("x = " + "+".join(["a"] * 150))
    assert pm.chains[0].operands[1].code == "ST-LIM-001"                       # 299 nodes: beyond the default 256
    pm = P("x = " + "+".join(["a"] * 100))
    assert pm.chains[0].operands[1].readings and depth(pm.chains[0].operands[1].node) == 2   # a flat sum is not deep


# ---------------------------------------------------------------- AST helpers

def test_helpers():
    n = node("(v − u)/t")
    assert symbols(n) == ("v", "u", "t") and not is_closed(n)
    num = node("(20 − 0)/4.0")
    assert is_closed(num) and node_count(num) == 5 and [type(x).__name__ for x in walk(num)][0] == "BinOp"
    pairs = align(n, num)
    assert [(render(a), render(b)) for a, b in pairs] == [("v", "20"), ("u", "0"), ("t", "4.0")]
    assert align(node("m·c·ΔT"), node("0.50 × 4200 × 20")) is not None
    assert align(node("v + u"), node("3 × 4")) is None
    assert shape_key(node("2 × 3")) == shape_key(node("2·3")) == shape_key(node("2*3"))
    v = value_of(node("−25%"))
    assert v[0] == -25 and v[3] == "%" and is_value(node("−25%"))
    assert value_of(node("3.0 m"))[2].text == "m"
    assert value_of(node("x")) is None
    assert render(node("2.0 × (3 ± 1)")) == "2.0 × (3 ± 1)"


def test_parse_is_linear_in_span_length():
    text = " + ".join(f"{i}.0" for i in range(1, 120))
    t = time.perf_counter()
    for _ in range(20):
        P("x = " + text)
    assert time.perf_counter() - t < 2.0
    assert Fraction(1) == 1
