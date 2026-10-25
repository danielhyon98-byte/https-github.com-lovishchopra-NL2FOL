"""Link classification, sequences, results, givens, targets and check planning (docs/STEM_DESIGN.md, sections 5 and 7)."""
from __future__ import annotations

import pytest

from epinoic_logic.stem import CHECK_KINDS, ST_SEVERITY, build_document
from epinoic_logic.stem.limits import StemLimits
from epinoic_logic.stem.nodes import render


def doc(text: str, request: str | None = None, profile: str = "physics", **kw):
    return build_document(text, request, profile, **kw)


def rels(d) -> list[tuple[str, str, str]]:
    return [(r.check_id, r.kind, r.outcome) for r in d.relations]


def checks(d) -> list[tuple[str, str]]:
    return [(r.check_id, r.kind) for r in d.checks]


def codes(d) -> list[str]:
    return [f.code for f in d.findings]


def side(op) -> str:
    return " | ".join(render(r) for r in op.readings) if op is not None and op.readings else "?"


# ---------------------------------------------------------------- equalities, substitutions, conversions

def test_formula_substitution_and_evaluation():
    d = doc("Given: m = 2.0 kg, v = 3.0 m s⁻¹.\nKE = ½mv² = ½ × 2.0 × 3.0² = 9.0 J", "A 2.0 kg mass moves at 3.0 m s⁻¹. Calculate its kinetic energy.")
    assert checks(d) == [("stem-giv-1", "giv"), ("stem-giv-2", "giv"), ("stem-sub-1", "sub"), ("stem-eq-1", "eq")]   # document order
    sub = d.check("stem-sub-1")
    assert [(n, render(x)) for n, x in sub.pairs] == [("m", "2.0"), ("v", "3.0")] and sub.statement_ids == ("s1.2",)
    assert sub.formula is None                       # aligned inside its own chain
    eq = d.check("stem-eq-1")
    assert side(eq.left) == "½ × 2.0 × 3.0^2" and side(eq.right) == "9.0 [J]"
    formula = [r for r in d.relations if r.kind == "formula"][0]
    assert formula.outcome == "formula"


def test_substitution_into_a_recorded_formula():
    d = doc("Given u = 0, a = 9.8 m s⁻², t = 3.0 s.\nv = u + at\nv = 0 + 9.8 × 3.0 = 29.4 m s⁻¹")
    sub = [r for r in d.checks if r.kind == "sub"][0]
    assert sub.formula is not None and sub.formula.statement_id == "s1.2" and render(sub.formula.expr) == "u + a·t"
    assert sorted(n for n, _x in sub.pairs) == ["a", "t", "u"]


def test_substitution_into_unbound_symbols_introduces_values():
    d = doc("v = d/t = 100/9.58 = 10.4 m s⁻¹")
    assert rels(d) == [("", "formula", "formula"), ("", "sub", "binding"), ("stem-eq-1", "eq", "check")]
    assert d.substitutions["d"][0].value == 100 and not d.bindings.get("d")


def test_partial_symbolic_substitution_is_never_an_identity():
    d = doc("v = u + at = 0 + g × 2.0")
    sub = [r for r in d.relations if r.kind == "sub"][0]
    assert [(n, render(x)) for n, x in sub.pairs] == [("u", "0"), ("a", "g"), ("t", "2.0")]
    assert not [r for r in d.relations if r.kind == "alg"]


def test_continuation_lines_are_read_as_links_across_the_lines_of_one_statement():
    # the equation continued on lines that open with '=' is one statement (round 7); its links still join the lines
    text = "v = u + at\n= 0 + 9.8 × 2.0\n= 19.6 m s⁻¹"
    d = doc(text)
    eq = d.check("stem-eq-1")
    assert eq.statement_ids == ("s1.1",) and text[eq.start:eq.end] == "0 + 9.8 × 2.0\n= 19.6 m s⁻¹"
    sub = [r for r in d.relations if r.kind == "sub"][0]
    assert sub.statement_ids == ("s1.1",) and text[sub.start:sub.end] == "u + at\n= 0 + 9.8 × 2.0"


@pytest.mark.parametrize("text, kind", [("72 km h⁻¹ = 20 m s⁻¹", "cnv"), ("25 °C = 298 K", "cnv"), ("2 + 3 = 5", "eq"), ("3.0 m s⁻¹ > 2.0 m s⁻¹", "cmp")])
def test_closed_relations(text, kind):
    assert checks(doc(text)) == [(f"stem-{kind}-1", kind)]


def test_based_numerals_are_base_checks():
    assert checks(doc("FF₁₆ = 255", profile="computer_science")) == [("stem-base-1", "base")]
    assert checks(doc("0b1010 = 10", profile="mathematics_aa")) == [("stem-base-1", "base")]


# ---------------------------------------------------------------- algebra, roots, steps

def test_algebra_steps_with_premises():
    d = doc("2x + 3 = 11\n2x = 8\nx = 4", profile="mathematics_aa")
    assert checks(d) == [("stem-alg-1", "alg"), ("stem-alg-2", "alg")]
    a1 = d.check("stem-alg-1")
    assert side(a1.premise_left) == "2·x + 3" and side(a1.premise_right) == "11" and a1.premise_ids == ("s1.1",)
    assert side(a1.left) == "2·x" and side(a1.right) == "8" and a1.statement_ids == ("s1.1", "s1.2")


def test_roots_of_a_quadratic():
    d = doc("x² − 5x + 6 = 0\n(x − 2)(x − 3) = 0\nx = 2 or x = 3", profile="mathematics_aa")
    sol = d.check("stem-sol-1")
    assert sol.root_symbol == "x" and [render(r) for r in sol.roots] == ["2", "3"] and sol.complete and not sol.restricted
    assert side(sol.premise_left) == "(x - 2)·(x - 3)"
    assert [b.source for b in d.bindings["x"]] == ["root", "root"]


def test_principal_root_rule_per_profile():
    sci = doc("x² = 9 so x = 3", profile="physics")
    assert "ST-ALG-001" not in codes(sci)
    maths = doc("x² = 9 so x = 3", profile="mathematics_aa")
    f = [f for f in maths.findings if f.code == "ST-ALG-001"]
    assert f and f[0].check_id == "stem-alg-1" and f[0].severity == "warning"
    assert maths.check("stem-sol-1").complete is False


def test_inequality_step_is_cmp_with_premise():
    d = doc("x > 2 ⇒ 2x > 4", profile="mathematics_aa")
    cmp = d.check("stem-cmp-1")
    assert side(cmp.premise_left) == "x" and cmp.premise_op == ">" and cmp.explicit


def test_identity_inside_one_chain():
    d = doc("y = (x + 1)² = x² + 2x + 1", profile="mathematics_aa")
    alg = d.check("stem-alg-1")
    assert side(alg.left) == "(x + 1)^2" and side(alg.right) == "x^2 + 2·x + 1"


# ---------------------------------------------------------------- results, givens, targets

def test_result_restatement_needs_a_cue():
    plain = doc("v = 100/9.58 = 10.4 m s⁻¹\nThe speed is 10.4 m s⁻¹.")
    assert not [c for c in plain.checks if c.kind == "res"]
    cued = doc("v = 100/9.58 = 10.4 m s⁻¹\nSo the speed is 10.4 m s⁻¹.")
    res = cued.check("stem-res-1")
    assert res.statement_ids == ("s1.1", "s1.2") and side(res.left) == "10.4 [m s⁻¹]"


def test_givens_against_the_request():
    d = doc("Given: m = 0.20 kg.\nF = ma = 0.20 × 3.0 = 0.60 N", "A 0.20 kg ball accelerates at 3.0 m s⁻².")
    giv = d.check("stem-giv-1")
    assert [c.number.text for c in giv.candidates] == ["0.20"] and giv.statement_ids == ("s1.1",)


def test_show_that_target():
    req = "Show that the speed is about 10 m s⁻¹."
    d = doc("v = 100/9.58 = 10.4 m s⁻¹ ≈ 10 m s⁻¹", req)
    assert [c.kind for c in d.checks if c.kind == "tgt"] == ["tgt"]
    assert d.request.targets


# ---------------------------------------------------------------- chemistry, Boolean, tables

def test_chemistry_boolean_and_truth_table_checks():
    assert checks(doc("CaCO₃ → CaO + CO₂", profile="chemistry")) == [("stem-chem-1", "chem")]
    bad = doc("Ch₄ + O₂ → CO₂", profile="chemistry")
    assert not bad.checks and "ST-CHEM-001" in codes(bad)
    cs = doc("| A | B | A AND B |\n|---|---|---|\n| 0 | 0 | 0 |\n| 0 | 1 | 0 |\n| 1 | 0 | 0 |\n| 1 | 1 | 1 |\n\nAlso A AND B = B AND A.\n\n"
             "```python\nx = 1\n```", profile="computer_science")
    assert checks(cs) == [("stem-tt-1", "tt"), ("stem-bool-1", "bool")]
    code = [f for f in cs.findings if f.code == "ST-CODE-001"]
    assert code and code[0].severity == "info"


# ---------------------------------------------------------------- findings

def test_dimension_and_unit_findings():
    assert "ST-DIM-002" in codes(doc("F = 2.0 kg + 3.0 m"))
    assert "ST-UNIT-001" in codes(doc("E = 5.0 kg yr⁻¹"))
    amb = [f for f in doc("v = 3.0 ms⁻¹").findings if f.code == "ST-UNIT-002"]
    assert amb and amb[0].severity == "info"
    d = doc("m = 2.0 kg, a = 3.0 m s⁻²\nF = ma = 2.0 × 3.0 = 6.0 kg")
    dim = [f for f in d.findings if f.code == "ST-DIM-001"]
    assert len(dim) == 1 and dim[0].check_id == "stem-eq-1" and "m·a" in dim[0].message
    assert "ST-DIM-001" not in codes(doc("m = 2.0 kg, a = 3.0 m s⁻²\nF = ma = 2.0 × 3.0 = 6.0 N"))
    two_sided = doc("0.50 kg × 4200 J kg⁻¹ K⁻¹ × 20 K = 4.2 × 10⁴ J kg⁻¹")
    assert codes(two_sided).count("ST-DIM-001") == 1


@pytest.mark.parametrize("text, profile, reason", [
    # STEM repair 10 (rule definite-integral): a definite integral of a polynomial is checked now ('∫₀¹ x dx = 1/2' holds, tests/stem/
    # test_stem_repair10.py); an integral of anything else stays outside the encodings
    ("∫₀¹ √x dx = 2/3", "mathematics_aa", "an integral"),
    # STEM repair 11 (rule derivative): a derivative of a polynomial is checked now by the power rule ('d/dx (x²) = 2x' holds, '= x' fails,
    # tests/stem/test_stem_repair11.py); a derivative of anything else stays outside the encodings
    ("d/dx (sin x) = cos x", "mathematics_aa", "a derivative"),
    ("3x = 12 → x = 4", "mathematics_aa", "an arrow"),
])
def test_relations_outside_the_encodings_are_undecided(text, profile, reason):
    d = doc(text, profile=profile)
    und = [r for r in d.relations if r.outcome == "undecided"]
    assert und and und[0].code == "ST-UNDEC-001" and reason in und[0].reason
    f = [f for f in d.findings if f.code == "ST-UNDEC-001"]
    assert f and "not checked" in f[0].message


def test_formula_with_unsupported_notation_is_a_formula():
    d = doc("FV = PV(1 + r)^n", profile="mathematics_ai")
    assert rels(d) == [("", "formula", "formula")] and not d.findings


def test_front_end_emits_no_error_severity():
    texts = ["F = 2.0 kg + 3.0 m", "∫ x dx = 1", "Ch₄ → C", "x² = 9 so x = 3", "x = " + "(" * 40 + "1" + ")" * 40, "а = 3", "v = 3.0 ms⁻¹"]
    for t in texts:
        for prof in ("physics", "chemistry", "mathematics_aa", "computer_science"):
            assert all(f.severity in ("info", "warning") for f in doc(t, profile=prof).findings)
    assert set(ST_SEVERITY.values()) <= {"info", "warning"}


# ---------------------------------------------------------------- ids and caps

def test_check_ids_are_stable_per_kind_in_document_order():
    text = "2 + 2 = 4\nv = 3.0 m s⁻¹\n72 km h⁻¹ = 20 m s⁻¹\n3 + 3 = 6\n5 > 4"
    a = checks(doc(text))
    assert a == [("stem-eq-1", "eq"), ("stem-cnv-1", "cnv"), ("stem-eq-2", "eq"), ("stem-cmp-1", "cmp")]
    from epinoic_logic.stem import clear_document_cache
    clear_document_cache()
    assert checks(doc(text)) == a
    assert all(c.check_id.split("-")[1] in CHECK_KINDS for c in doc(text).checks)


def test_check_cap_is_st_lim_002():
    text = "\n".join(f"{i} + {i} = {2 * i}" for i in range(1, 140))
    d = doc(text, profile="mathematics_aa")
    assert len(d.checks) == 128 and d.checks[-1].check_id == "stem-eq-128"
    lim = [f for f in d.findings if f.code == "ST-LIM-002"]
    assert lim and "139 STEM checks" in lim[0].message and "stem-eq-129" in lim[0].message
    assert len(d.unchecked) == 11 and all(r.capped for r in d.unchecked)
    small = doc(text, profile="mathematics_aa", limits=StemLimits(max_checks_per_report=5))
    assert len(small.checks) == 5


def test_findings_are_deduplicated():
    d = doc("v = 3.0 ms⁻¹ = 3.0 ms⁻¹")
    assert codes(d).count("ST-UNIT-002") == 1


def test_verbal_arithmetic_is_read_end_to_end():
    d = doc("3 plus 4 equals 7, and 2.5 multiplied by 4 equals 10.")
    assert [(c.check_id, side(c.left), side(c.right)) for c in d.checks] == [("stem-eq-1", "3 + 4", "7"), ("stem-eq-2", "2.5 × 4", "10")]
    assert d.check("stem-eq-2").left.node.right.number.value == 4 and not d.findings
