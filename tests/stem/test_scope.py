"""Name pre-pass, bindings with provenance and formulas (docs/STEM_DESIGN.md, section 4.6)."""
from __future__ import annotations

import time
from fractions import Fraction

from epinoic_logic.stem import build_document
from epinoic_logic.stem.limits import StemLimits
from epinoic_logic.stem.nodes import Sym
from epinoic_logic.stem.numbers import scan_number
from epinoic_logic.stem.scope import Binding, Formula, Scope, prescan_names, si_value
from epinoic_logic.stem.units import parse_unit


def binding(symbol: str, text: str, unit: str = "", source: str = "statement", sid: str = "s1.1") -> Binding:
    sign = -1 if text.startswith("-") else 1
    num = scan_number(text.lstrip("-"), 0).number
    return Binding(symbol, sign * num.value, num, parse_unit(unit) if unit else None, source, sid)


# ---------------------------------------------------------------- name pre-pass

def test_prescan_declared_names():
    names = prescan_names("PV = 5000, F_net = ma, pV = nRT, ΔH° = -57, v₀ = 3, θ ≈ 0.5, v_{max} = 2, KE = 3, T½ = 2")
    assert {"PV", "F_net", "pV", "ΔH_°", "v_0", "θ", "v_max", "KE", "T_half"} <= names


def test_prescan_rejects_words_operators_and_comparisons():
    names = prescan_names("The answer = 5. We have mg = 3 + ma = 2, so 3 + x = 4 and a <= b, c >= d, e != f, g == h. reaction = fast")
    assert "answer" not in names and "reaction" not in names        # long words
    assert "ma" not in names and "x" not in names                    # after an operator
    assert not ({"a", "c", "e", "g"} & names)                        # comparisons are not declarations
    assert "mg" in names
    assert "so" not in prescan_names("so = 3")                      # a stop word


def test_prescan_is_linear_and_never_recurses():
    for text in ("a == b " * 50000, "==" * 200000, "x ≈ 1 = " * 40000, "x = " * 100000):
        t = time.perf_counter()
        prescan_names(text)
        assert time.perf_counter() - t < 1.0


def test_document_survives_repeated_comparison_operators():
    doc = build_document("a == b " * 3000, None, "mathematics_aa")
    assert not any(f.code == "ST-INTERNAL-001" for f in doc.findings)


# ---------------------------------------------------------------- bindings

def test_si_value_and_binding_tolerance():
    assert si_value(Fraction(5), parse_unit("km")) == 5000
    assert si_value(Fraction(25), None, "%") == Fraction(1, 4)
    assert si_value(Fraction(25), parse_unit("°C")) is None           # affine units only by explicit conversion
    assert si_value(Fraction(3), parse_unit("ms⁻¹")) is None          # two readings
    a = binding("v", "5.0", "m s⁻¹")
    assert a.half_width == Fraction(1, 20) and a.si == 5
    assert a.same_as(binding("v", "5.04", "m s⁻¹"))
    assert not a.same_as(binding("v", "5.2", "m s⁻¹"))
    assert binding("d", "1.5", "km").same_as(binding("d", "1500", "m"))   # compared in SI


def test_rebinding_notes_and_sources():
    sc = Scope()
    assert sc.add(binding("v", "5.0", "m s⁻¹", "given", "s1.1")) is None
    assert sc.add(binding("v", "5.02", "m s⁻¹", "statement", "s1.2")) is None     # equal within rounding
    note = sc.add(binding("v", "7.0", "m s⁻¹", "statement", "s2.1"))
    assert note is not None and note.code == "ST-SCOPE-001" and note.statement_ids == ("s1.2", "s2.1")
    assert sc.add(binding("x", "5", source="root", sid="s3.1")) is None
    assert sc.add(binding("x", "-2", source="root", sid="s3.1")) is None          # both roots: no rebinding
    assert sc.is_bound("x") and not sc.is_given("x")                                # a solved-for unknown stays unknown
    assert sc.is_given("v")
    assert sc.add(binding("m", "5.0", source="substitution")) is None
    assert not sc.is_bound("m") and sc.has_reading("m") and sc.substitutions["m"][0].value == 5
    assert [b.order for b in sc.bindings_for("v")] == [1, 2, 3]


def test_binding_bound_drops_the_oldest_with_a_note():
    sc = Scope(limits=StemLimits(max_bindings_per_symbol=3))
    for i, text in enumerate(("1", "2", "3", "4")):
        sc.add(binding("n", text, sid=f"s1.{i + 1}"))
    assert [b.number.text for b in sc.bindings_for("n")] == ["2", "3", "4"]
    assert any("more than 3 bindings" in n.message and n.statement_ids == ("s1.1",) for n in sc.notes)


def test_formulas_most_recent_last():
    sc = Scope()
    sc.add_formula(Formula("F", Sym("ma"), "s1.1", "law"))
    sc.add_formula(Formula("F", Sym("kx"), "s2.1", "law"))
    assert sc.formula_for("F").statement_id == "s2.1" and sc.formula_for("G") is None
    assert "F" in sc.names


# ---------------------------------------------------------------- scope in a document

def test_document_bindings_carry_provenance():
    doc = build_document("Given: m = 2.0 kg, v = 3.0 m s⁻¹.\nKE = ½mv² = ½ × 2.0 × 3.0² = 9.0 J", "A 2.0 kg mass moves at 3.0 m s⁻¹.", "physics")
    m = doc.bindings["m"][0]
    assert m.source == "given" and m.statement_id == "s1.1" and m.unit.text == "kg" and m.number.sig_figs == 2
    assert doc.statement_text(m.statement_id).startswith("Given:")
    ke = doc.bindings["KE"]
    assert ke[-1].source == "result" and ke[-1].value == 9
    assert "KE" in doc.formulas and doc.formulas["KE"][0].source in ("law", "definition")
    assert not doc.findings or all(f.severity != "error" for f in doc.findings)


def test_part_b_reusing_a_letter_is_noted_not_flagged():
    doc = build_document("(a) v = 3.0 m s⁻¹\n(b) v = 5.0 m s⁻¹", None, "physics")
    notes = [f for f in doc.findings if f.code == "ST-SCOPE-001"]
    assert len(notes) == 1 and notes[0].severity == "info" and notes[0].statement_ids == ("s1.1", "s1.2")
    assert [b.source for b in doc.bindings["v"]] == ["statement", "statement"]     # a value binding is no equation whose roots follow


def test_roots_are_not_rebindings():
    doc = build_document("x² − 5x + 6 = 0, so (x − 2)(x − 3) = 0 and x = 2 or x = 3.", None, "mathematics_aa")
    assert [(b.number.text, b.source) for b in doc.bindings["x"]] == [("2", "root"), ("3", "root")]
    assert not [f for f in doc.findings if f.code == "ST-SCOPE-001"]
