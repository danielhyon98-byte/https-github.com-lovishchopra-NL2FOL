"""Items of the STEM corpus: probe answers, extra labels for the fixture items, and templates.

Each template writes one answer in one notation (``R``: unicode, ascii, latex inline, LaTeX
display) with every relation it states as a :class:`Step`, and the manual mutants of the fault
catalogue that need more than a changed figure (a substituted value, an operator, a given, a
dropped factor, a unit, a rearrangement, a root, a balance, an identity, a row, a base, a
comparison, a target). Automatic mutants (a slip of the stated result, a power of ten, a sign)
and rounding controls are added by the builder. Formula answers are written from expression
trees (``corpus_dsl.E``) that also compute the exact values, so the text and the label agree by
construction. Nothing here reads item text for meaning.
"""
from __future__ import annotations

from fractions import Fraction as F
from typing import Optional

from corpus_dsl import (HALF_E, NOTATION_TAGS, E, X, Item, Mut, N, R, S, Step, add, disjoint_proof, div, fault_proof, minus, mismatch_proof, mul, neg, pw,
                        render, replace_node, sig_figs, subst, sup, value, walk)
from corpus_lib import Iv, W, leading_digit_slip, point, round_sig, widest

ITEMS: list[Item] = []
PROBES: list[dict] = []
FIXTURE_LABELS: dict[str, dict] = {
    # the stem-sol completeness check names the closing claim 'x = 8 is the solution', which carries the lost root forward
    "stem-math-021": {"affected_steps": ["x = 8 is the solution"]},
    # STEM repair 11 (rule derivative): the wrong derivative is decided now, by the algebra check against the power rule's derivative
    "stem-math-012": {"check_kinds": ["alg"]},
}


def catalogue(cls: str):
    from build_stem_corpus import CATALOGUE
    return CATALOGUE[cls]


def add_item(it: Item) -> Item:
    ITEMS.append(it)
    return it


def tags(r: R, *extra: str) -> list[str]:
    return [NOTATION_TAGS[r.nota], *extra]


def holds(**kw) -> dict:
    kw.setdefault("holds", True)
    return kw


def mut(cls: str, target: str, repl, prf: dict, note: str, *, kinds=None, affected=()) -> Mut:
    codes, k, sev = catalogue(cls)
    return Mut(cls, target, list(repl), tuple(codes), tuple(kinds if kinds is not None else k), dict(prf), note, affected=tuple(affected), severity=sev)


def key_of(name: str, subscript: str = "") -> str:
    return name + ("_" + subscript if subscript else "")


AUTO = ("slip", "pow10", "sign", "round", "res")


def _num_text(r: R, spec: str) -> str:
    if "e" in spec:
        m, x = spec.split("e")
        return r.sci(r.num(m), int(x))
    return r.num(spec)


def _to_sci(spec: str, sf: int) -> tuple[str, int]:
    v = F(spec)
    e = 0
    a = abs(v)
    while a >= 10:
        a /= 10
        e += 1
    while 0 < a < 1:
        a *= 10
        e -= 1
    m = round_sig(v / F(10) ** e, sf)
    if abs(F(m)) >= 10:
        m = round_sig(F(m) / 10, sf)
        e += 1
    return m, e


def _same_form(C: F, like: str, sf: int) -> str:
    if "e" in like:
        m, x = _to_sci(round_sig(C, sf), sf)
        return f"{m}e{x}"
    return round_sig(C, sf)


# ===================================================================================== formula answers
def formula_item(ident: str, subject: str, topic: str, nota: str, question: str, givens: list, lhs: tuple, formula: E, sf: int, unit: str,
                 restate: str, *, style: str = "block", intro: str = "Using", wrong_unit: Optional[str] = None, auto=AUTO, sub_slip: Optional[str] = None,
                 drop: bool = False, operator: bool = True, misstate: Optional[str] = None, sci: bool = False, result_spec: Optional[str] = None,
                 extra_tags=()) -> Item:
    """``lhs = formula = substitution = result unit``, with the given values before it and a restatement after it.

    ``givens``: ``(name, subscript, spec, unit key or None)``; ``style``: ``block`` ("Given: …", checked against the
    request), ``with`` ("With … and …, …": a let binding) or ``request`` (the values are bound in the request only)."""
    r = R(nota)
    ru = R("unicode")
    env = {key_of(n, s): spec for n, s, spec, _u in givens}
    num = subst(formula, env)
    C = value(formula, point, env)
    if result_spec is None:
        result_spec = round_sig(C, sf)
        while not sci and "." not in result_spec and result_spec.endswith("0") and F(result_spec) != C:
            sf += 1  # an integer whose trailing zeros are not significant: write the figures instead (section 5.1)
            result_spec = round_sig(C, sf)
        if sci:
            m, x = _to_sci(result_spec, sf)
            result_spec = f"{m}e{x}"
    Ltext = r.sym(*lhs)
    Ftext, Ntext = render(formula, r), render(num, r)
    S_text = _num_text(r, result_spec)
    U = r.u(unit) if unit else ""
    sep = ("\\," if r.latex else " ") if unit else ""
    if r.latex:
        parts = [f"${r.sym(n, s)} = {_num_text(r, spec)}{(sep + r.u(u)) if u else ''}$" for n, s, spec, u in givens]
    else:
        parts = [f"{r.sym(n, s)} = {_num_text(r, spec)}{(' ' + r.u(u)) if u else ''}" for n, s, spec, u in givens]
    joiner = " and " if style == "with" else ", "
    gtext = ", ".join(parts[:-1]) + (joiner if len(parts) > 1 else "") + parts[-1] if parts else ""
    chain = f"{Ltext} = {Ftext} = {Ntext} = {S_text}{sep}{U}"
    if nota == "display":
        res_text = f"{restate} {_num_text(ru, result_spec)}{(' ' + ru.u(unit)) if unit else ''}"
        lead = {"block": f"Given: {gtext}.\n{intro}:", "with": f"With {gtext}:", "request": f"{intro}:"}[style]
        resp = f"{lead}\n\\[ {chain} \\]\n{res_text}."
    else:
        res_text = f"{restate} ${S_text}{sep}{U}$" if r.latex else f"{restate} {S_text}{sep}{U}"
        line = f"${chain}$" if r.latex else chain
        lead = {"block": f"Given: {gtext}.\n{intro} ", "with": f"With {gtext}, ", "request": f"{intro} "}[style]
        resp = f"{lead}{line}. {res_text}."
    sub_text = f"{Ftext} = {Ntext}"
    eq_text = f"{Ntext} = {S_text}{sep}{U}"
    steps = []
    if style == "block":
        steps.append(Step("giv", gtext, "giv", proof=holds(rule="each Given value is the request's value", values=[g[2] for g in givens])))
    elif style == "with":
        steps.append(Step("bind", gtext, "bind", proof=holds(rule="values stated for symbols; not a check")))
    sci_t = None
    if "e" in result_spec:
        m, x = result_spec.split("e")
        sci_t = (m, int(x), r)
    res_r = ru if nota == "display" else r
    steps += [Step("sub", sub_text, "sub", deps=("giv", "bind"), proof=holds(rule="the substituted values are the bindings", values=env)),
              Step("eq", eq_text, "eq", deps=("sub", "giv", "bind"), expr=lambda v, _n=num: value(_n, v), S=result_spec, S_text=S_text, sci=sci_t),
              Step("res", res_text, "res", deps=("eq",), expr=lambda v, _s=result_spec: v(_s), S=result_spec, S_text=_num_text(res_r, result_spec),
                   sci=(sci_t[0], sci_t[1], res_r) if sci_t else None)]
    unit_tag = {"unicode": "units_unicode_exponent", "ascii": "units_slash", "latex": "units_latex", "display": "units_latex"}[nota]
    it = add_item(Item(ident, subject, question, resp, tags(r, unit_tag, *extra_tags), steps, r=r, topic=topic, auto=auto))

    def res_edit(new: str) -> tuple:
        return (_num_text(res_r, result_spec), _num_text(res_r, new), res_text, "last")

    # a substituted value that differs from its binding, the arithmetic consistent with it
    if sub_slip is not None:
        g = next(x for x in givens if key_of(x[0], x[1]) == sub_slip)
        new_spec = leading_digit_slip(g[2])
        env2 = dict(env, **{sub_slip: new_spec})
        num2 = subst(formula, env2)
        s2 = _same_form(value(num2, point), result_spec, sf)
        if s2 != result_spec:
            repl = [(Ntext, render(num2, r), sub_text), (S_text, _num_text(r, s2), eq_text, "last"), res_edit(s2)]
            it.muts.append(mut("wrong_substitution", "sub", repl, mismatch_proof(g[2], new_spec, f"substituted {sub_slip} against its binding"),
                               f"{sub_slip} = {g[2]} was substituted as {new_spec}; the arithmetic ({s2}) is consistent with it", affected=("eq", "res")))
    # an operator changed in the numeric side, the stated result unchanged
    if operator:
        target = next((x for x in walk(num) if x.op in ("sub", "add")), None) or next((x for x in walk(num) if x.op == "mul" and not x.implicit), None)
        if target is not None:
            swap = {"sub": "add", "add": "sub", "mul": "div"}[target.op]
            num3 = replace_node(num, target, E(swap, target.args, target.val, target.sub, target.const, False))
            t3 = render(num3, r)
            prf = fault_proof(lambda v, _n=num3: value(_n, v), result_spec)
            if prf["fails"] and t3 != Ntext:
                it.muts.append(mut("wrong_operator", "eq", [(Ntext, t3, eq_text)], prf, f"a {target.op} became a {swap} in the substitution; the stated result is unchanged"))
    # a coefficient (½, 2, a fraction) dropped from the substitution, the arithmetic consistent with it
    if drop:
        coef = next((x for x in walk(num) if x.op in ("half", "frac") or (x.op == "int" and x.val in ("2", "4"))), None)
        if coef is not None:
            num4 = replace_node(num, coef, None)
            s4 = _same_form(value(num4, point), result_spec, sf)
            prf = disjoint_proof(Iv.of(value(formula, widest, env)), Iv.of(value(num4, widest)), "the formula under its bindings against the written substitution")
            if prf["fails"] and s4 != result_spec:
                repl = [(Ntext, render(num4, r), sub_text), (S_text, _num_text(r, s4), eq_text, "last"), res_edit(s4)]
                it.muts.append(mut("dropped_factor", "sub", repl, prf, f"the factor {render(coef, ru)} was dropped from the substitution; the arithmetic ({s4}) is consistent "
                                   "with it", kinds=("sub",), affected=("eq", "res")))
    # a Given value misstated against the request, everything after it consistent with it
    if misstate is not None and style == "block":
        g = next(x for x in givens if key_of(x[0], x[1]) == misstate)
        new_spec = leading_digit_slip(g[2])
        env5 = dict(env, **{misstate: new_spec})
        num5 = subst(formula, env5)
        s5 = _same_form(value(num5, point), result_spec, sf)
        old_g = f"{r.sym(g[0], g[1])} = {_num_text(r, g[2])}"
        new_g = f"{r.sym(g[0], g[1])} = {_num_text(r, new_spec)}"
        if s5 != result_spec:
            repl = [(old_g, new_g, gtext), (Ntext, render(num5, r), sub_text), (S_text, _num_text(r, s5), eq_text, "last"), res_edit(s5)]
            it.muts.append(mut("misstated_given", "giv", repl, mismatch_proof(g[2], new_spec, "the answer's Given value against the request's"),
                               f"the request states {misstate} = {g[2]}; the answer's Given says {new_spec} and works consistently with it",
                               affected=("sub", "eq", "res")))
    # the result written in a unit of another dimension
    if wrong_unit is not None:
        Wu = r.u(wrong_unit)
        k = res_text.rfind(res_r.u(unit))
        res_new = res_text[:k] + res_r.u(wrong_unit) + res_text[k + len(res_r.u(unit)):]
        it.muts.append(mut("dimension_error", "eq", [(U, Wu, eq_text, "last"), (res_text, res_new)],
                           {"rule": f"the formula's dimension under the bound units is that of {unit}; {wrong_unit} has another", "fails": True},
                           f"the result is written in {wrong_unit} instead of {unit}", affected=("res",)))
    return it


# ============================================================================================ PHYSICS
PHYS = "Physics"
for _k, (_nota, _u, _v, _t, _who) in enumerate([("unicode", "4.0", "11.0", "3.0", "cyclist"), ("ascii", "2.0", "9.5", "5.0", "car"),
                                                  ("latex", "1.5", "8.0", "2.5", "sprinter"), ("display", "1.0", "13.0", "4.0", "trolley")]):
    formula_item(f"phys-accel-{_k + 1}", PHYS, "kinematics", _nota,
                 f"A {_who} accelerates uniformly from {_u} m s⁻¹ to {_v} m s⁻¹ in {_t} s. Calculate the acceleration.",
                 [("u", "", _u, "m/s"), ("v", "", _v, "m/s"), ("t", "", _t, "s")], ("a", ""), div(minus(S("v"), S("u")), S("t")), 2, "m/s2",
                 "The acceleration is therefore", sub_slip="t", misstate="v", wrong_unit="m/s")

for _k, (_nota, _u, _a, _t) in enumerate([("unicode", "2.5", "1.2", "3.0"), ("latex", "4.0", "0.80", "5.0"), ("ascii", "1.5", "2.4", "2.0")]):
    formula_item(f"phys-suvat-{_k + 1}", PHYS, "kinematics", _nota,
                 f"A ball rolls with initial speed {_u} m s⁻¹ and uniform acceleration {_a} m s⁻² for {_t} s. Calculate the displacement.",
                 [("u", "", _u, "m/s"), ("a", "", _a, "m/s2"), ("t", "", _t, "s")], ("s", ""),
                 add(mul(S("u"), S("t"), implicit=True), mul(HALF_E, S("a"), pw(S("t"), 2), implicit=True)), 2, "m",
                 "The displacement is therefore", drop=True, sub_slip="a", wrong_unit="m/s")

for _k, (_nota, _m, _a) in enumerate([("ascii", "1200", "2.5"), ("display", "0.45", "3.2"), ("unicode", "75", "1.8")]):
    formula_item(f"phys-newton-{_k + 1}", PHYS, "forces", _nota,
                 f"A body of mass {_m} kg accelerates at {_a} m s⁻². Calculate the resultant force on it.",
                 [("m", "", _m, "kg"), ("a", "", _a, "m/s2")], ("F", ""), mul(S("m"), S("a"), implicit=True), 2, "N",
                 "The resultant force is therefore", sub_slip="m", misstate="a", wrong_unit="J")

for _k, (_nota, _style, _m, _v) in enumerate([("unicode", "with", "2.0", "3.5"), ("latex", "block", "0.15", "12"), ("display", "with", "65", "8.0"),
                                              ("ascii", "block", "1.6", "4.5")]):
    formula_item(f"phys-ke-{_k + 1}", PHYS, "energy", _nota,
                 f"Calculate the kinetic energy of a {_m} kg object moving at {_v} m s⁻¹.",
                 [("m", "", _m, "kg"), ("v", "", _v, "m/s")], ("E", "k"), mul(HALF_E, S("m"), pw(S("v"), 2), implicit=True), 2, "J",
                 "The kinetic energy is therefore", style=_style, drop=True, sub_slip="v", wrong_unit="W", misstate="v" if _style == "block" else None)

for _k, (_nota, _m, _h) in enumerate([("unicode", "2.0", "3.5"), ("latex", "55", "12.0")]):
    formula_item(f"phys-gpe-{_k + 1}", PHYS, "energy", _nota,
                 f"A {_m} kg mass is raised through a height of {_h} m. Calculate the gain in gravitational potential energy (g = 9.81 m s⁻²).",
                 [("m", "", _m, "kg"), ("g", "", "9.81", "m/s2"), ("h", "", _h, "m")], ("E", "p"), mul(S("m"), S("g"), S("h"), implicit=True), 3, "J",
                 "Hence the gain in gravitational potential energy is", style="with", sub_slip="h", wrong_unit="N")

for _k, (_nota, _w, _t) in enumerate([("unicode", "4500", "15"), ("ascii", "360", "8.0")]):
    formula_item(f"phys-power-{_k + 1}", PHYS, "energy", _nota,
                 f"A motor does {_w} J of work in {_t} s. Calculate its average power output.",
                 [("W", "", _w, "J"), ("t", "", _t, "s")], ("P", ""), div(S("W"), S("t")), 2, "W",
                 "The average power output is therefore", sub_slip="t", misstate="t", wrong_unit="J")

for _k, (_nota, _m, _v) in enumerate([("latex", "0.25", "18"), ("unicode", "1500", "22")]):
    formula_item(f"phys-momentum-{_k + 1}", PHYS, "momentum", _nota,
                 f"Calculate the momentum of a {_m} kg body moving at {_v} m s⁻¹.",
                 [("m", "", _m, "kg"), ("v", "", _v, "m/s")], ("p", ""), mul(S("m"), S("v"), implicit=True), 2, "kg m/s",
                 "The momentum is therefore", sub_slip="v", misstate="m", wrong_unit="N")

for _k, (_nota, _i, _r) in enumerate([("unicode", "0.40", "12"), ("ascii", "2.5", "4.8"), ("latex", "0.15", "220")]):
    formula_item(f"phys-ohm-{_k + 1}", PHYS, "electricity", _nota,
                 f"A current of {_i} A flows through a {_r} Ω resistor. Calculate the potential difference across it.",
                 [("I", "", _i, "A"), ("R", "", _r, "ohm")], ("V", ""), mul(S("I"), S("R"), implicit=True), 2, "V",
                 "The potential difference is therefore", sub_slip="I", misstate="R", wrong_unit="A")

for _k, (_nota, _i, _r) in enumerate([("display", "1.5", "8.0"), ("unicode", "0.30", "47")]):
    formula_item(f"phys-elpower-{_k + 1}", PHYS, "electricity", _nota,
                 f"A current of {_i} A flows through a {_r} Ω resistor. Calculate the power dissipated.",
                 [("I", "", _i, "A"), ("R", "", _r, "ohm")], ("P", ""), mul(pw(S("I"), 2), S("R"), implicit=True), 2, "W",
                 "The power dissipated is therefore", sub_slip="R", wrong_unit="J")

for _k, (_nota, _f, _l, _sci) in enumerate([("unicode", "5.0e14", "6.0e-7", True), ("ascii", "256", "1.35", False), ("latex", "440", "0.78", False)]):
    formula_item(f"phys-wave-{_k + 1}", PHYS, "waves", _nota,
                 f"A wave has frequency {_f.replace('e14', ' × 10¹⁴')} Hz and wavelength {_l.replace('e-7', ' × 10⁻⁷')} m. Calculate its speed.",
                 [("f", "", _f, "Hz"), ("λ", "", _l, "m")], ("v", ""), mul(S("f"), S("λ"), implicit=True), 2, "m/s",
                 "The wave speed is therefore", sci=_sci, sub_slip="f", wrong_unit="Hz", style="with" if _sci else "block", misstate=None if _sci else "λ")

for _k, (_nota, _m, _c, _dt) in enumerate([("unicode", "0.50", "4200", "12"), ("latex", "2.0", "900", "35")]):
    formula_item(f"phys-heat-{_k + 1}", PHYS, "thermal", _nota,
                 f"Calculate the energy needed to raise the temperature of {_m} kg of a material of specific heat capacity {_c} J kg⁻¹ K⁻¹ by {_dt} K.",
                 [("m", "", _m, "kg"), ("c", "", _c, "J/kgK"), ("ΔT", "", _dt, "K")], ("Q", ""), mul(S("m"), S("c"), S("ΔT"), implicit=True), 2, "J",
                 "The energy needed is therefore", sub_slip="m", misstate="m", wrong_unit="W")

for _k, (_nota, _n, _t, _p) in enumerate([("unicode", "0.50", "300", "1.0e5"), ("latex", "2.0", "273", "2.0e5")]):
    formula_item(f"phys-gas-{_k + 1}", PHYS, "thermal", _nota,
                 f"Calculate the volume of {_n} mol of an ideal gas at {_t} K and a pressure of {_p.replace('e5', ' × 10⁵')} Pa (R = 8.31 J mol⁻¹ K⁻¹).",
                 [("n", "", _n, "mol"), ("R", "", "8.31", "J/molK"), ("T", "", _t, "K"), ("p", "", _p, "Pa")], ("V", ""),
                 div(mul(S("n"), S("R"), S("T"), implicit=True), S("p")), 2, "m3", "So the volume of the gas is", style="with", sub_slip="T", wrong_unit="m2",
                 sci=True)

for _k, (_nota, _f) in enumerate([("unicode", "6.0e14"), ("latex", "4.5e14")]):
    formula_item(f"phys-photon-{_k + 1}", PHYS, "quantum", _nota,
                 f"Calculate the energy of a photon of frequency {_f.replace('e14', ' × 10¹⁴')} Hz (h = 6.63 × 10⁻³⁴ J s).",
                 [("h", "", "6.63e-34", "Js"), ("f", "", _f, "Hz")], ("E", ""), mul(S("h"), S("f"), implicit=True), 2, "J",
                 "The photon energy is therefore", style="with", sci=True, sub_slip="f", wrong_unit="W")

for _k, (_nota, _f, _a) in enumerate([("ascii", "450", "0.015"), ("display", "12", "0.0030")]):
    formula_item(f"phys-pressure-{_k + 1}", PHYS, "pressure", _nota,
                 f"A force of {_f} N acts on an area of {_a} m². Calculate the pressure.",
                 [("F", "", _f, "N"), ("A", "", _a, "m2")], ("p", ""), div(S("F"), S("A")), 2, "Pa",
                 "The pressure is therefore", sub_slip="F", misstate="A", wrong_unit="N")

for _k, (_nota, _m, _v) in enumerate([("unicode", "0.54", "2.0e-4"), ("ascii", "7.9", "0.0010")]):
    formula_item(f"phys-density-{_k + 1}", PHYS, "matter", _nota,
                 f"A block of mass {_m} kg has a volume of {_v.replace('e-4', ' × 10⁻⁴')} m³. Calculate its density.",
                 [("m", "", _m, "kg"), ("V", "", _v, "m3")], ("ρ", ""), div(S("m"), S("V")), 2, "kg/m3",
                 "The density is therefore", sub_slip="m", wrong_unit="kg", style="with" if "e" in _v else "block", misstate=None if "e" in _v else "m")


# ========================================================================================== CHEMISTRY
CHEM = "Chemistry"
for _k, (_nota, _style, _m, _M, _what) in enumerate([("unicode", "block", "9.0", "18.0", "water"), ("latex", "with", "4.4", "44.0", "carbon dioxide"),
                                                     ("ascii", "block", "5.85", "58.5", "sodium chloride"), ("display", "block", "12.5", "100.1", "calcium carbonate")]):
    formula_item(f"chem-moles-{_k + 1}", CHEM, "moles", _nota,
                 f"Calculate the amount of substance in {_m} g of {_what} (M = {_M} g mol⁻¹).",
                 [("m", "", _m, "g"), ("M", "", _M, "g/mol")], ("n", ""), div(S("m"), S("M")), 2, "mol",
                 "The amount of substance is therefore", style=_style, sub_slip="m", misstate="m", wrong_unit="g")

for _k, (_nota, _style, _n, _V) in enumerate([("unicode", "block", "0.0250", "0.500"), ("display", "with", "0.12", "0.250"), ("ascii", "block", "1.5", "2.0")]):
    formula_item(f"chem-conc-{_k + 1}", CHEM, "concentration", _nota,
                 f"{_n} mol of solute is dissolved to make {_V} dm³ of solution. Calculate the concentration.",
                 [("n", "", _n, "mol"), ("V", "", _V, "dm3")], ("c", ""), div(S("n"), S("V")), 3 if len(_n) > 4 else 2, "mol/dm3",
                 "The concentration is therefore", style=_style, sub_slip="V", misstate="n", wrong_unit="mol")

formula_item("chem-mass-1", CHEM, "moles", "ascii", "Calculate the mass of 0.250 mol of magnesium oxide (M = 40.3 g mol⁻¹).",
             [("n", "", "0.250", "mol"), ("M", "", "40.3", "g/mol")], ("m", ""), mul(S("n"), S("M"), implicit=True), 3, "g",
             "The mass is therefore", sub_slip="M", misstate="n", wrong_unit="mol")

for _k, (_nota, _c1, _v1, _v2) in enumerate([("unicode", "0.100", "25.0", "250.0"), ("latex", "2.00", "10.0", "50.0")]):
    formula_item(f"chem-dilution-{_k + 1}", CHEM, "concentration", _nota,
                 f"{_v1} cm³ of a {_c1} mol dm⁻³ solution is diluted to {_v2} cm³. Calculate the new concentration.",
                 [("c", "1", _c1, "mol/dm3"), ("V", "1", _v1, "cm3"), ("V", "2", _v2, "cm3")], ("c", "2"), div(mul(S("c", "1"), S("V", "1"), implicit=True), S("V", "2")),
                 3, "mol/dm3", "Hence the diluted concentration is", style="with", sub_slip="V_1", wrong_unit="mol")

for _k, (_nota, _m, _dt) in enumerate([("unicode", "50.0", "6.5"), ("ascii", "100.0", "12.0")]):
    formula_item(f"chem-heat-{_k + 1}", CHEM, "energetics", _nota,
                 f"{_m} g of water is heated by {_dt} K. Calculate the heat absorbed (c = 4.18 J g⁻¹ K⁻¹).",
                 [("m", "", _m, "g"), ("c", "", "4.18", "J/gK"), ("ΔT", "", _dt, "K")], ("Q", ""), mul(S("m"), S("c"), S("ΔT"), implicit=True), 3, "J",
                 "The heat absorbed is therefore", style="with", sub_slip="m", wrong_unit="K")

formula_item("chem-gasn-1", CHEM, "gases", "latex", "Calculate the amount of gas in 2.40 dm³ at 298 K and 101 kPa (R = 8.31 J mol⁻¹ K⁻¹).",
             [("p", "", "1.01e5", "Pa"), ("V", "", "2.40e-3", "m3"), ("R", "", "8.31", "J/molK"), ("T", "", "298", "K")], ("n", ""),
             div(mul(S("p"), S("V"), implicit=True), mul(S("R"), S("T"), implicit=True)), 3, "mol", "The amount of gas is therefore", style="with",
             sub_slip="T", wrong_unit="g")

formula_item("chem-avogadro-1", CHEM, "moles", "unicode", "How many molecules are there in 0.250 mol of water (N_A = 6.02 × 10²³ mol⁻¹)?",
             [("n", "", "0.250", "mol"), ("N", "A", "6.02e23", None)], ("N", ""), mul(S("n"), S("N", "A"), implicit=True), 3, None,
             "The number of molecules is therefore", style="with", sci=True, sub_slip="n", operator=False)

# ============================================================================================ BIOLOGY
BIO = "Biology"
for _k, (_nota, _N1, _N2, _m) in enumerate([("unicode", "40", "36", "6"), ("latex", "25", "30", "5")]):
    formula_item(f"bio-lincoln-{_k + 1}", BIO, "ecology", _nota,
                 f"In a capture-mark-recapture study {_N1} snails were marked; later {_N2} were caught, of which {_m} were marked. Estimate the population size.",
                 [("n", "1", _N1, None), ("n", "2", _N2, None), ("m", "", _m, None)], ("N", ""), div(mul(S("n", "1"), S("n", "2")), S("m")), 3, None,
                 "The population is therefore estimated at", style="with", sub_slip="m", auto=("slip", "sign"))

for _k, (_nota, _q) in enumerate([("unicode", "0.30"), ("ascii", "0.45")]):
    formula_item(f"bio-hw-{_k + 1}", BIO, "genetics", _nota,
                 f"In a population at Hardy–Weinberg equilibrium the frequency of the recessive allele is q = {_q}. Calculate the frequency of the dominant allele p.",
                 [("q", "", _q, None)], ("p", ""), minus(X(1), S("q")), 2, None, "The frequency of the dominant allele is therefore", style="request",
                 auto=("slip", "sign"))

for _k, (_nota, _p, _q) in enumerate([("unicode", "0.70", "0.30"), ("display", "0.55", "0.45")]):
    formula_item(f"bio-het-{_k + 1}", BIO, "genetics", _nota,
                 f"Allele frequencies are p = {_p} and q = {_q}. Calculate the frequency of heterozygotes.",
                 [("p", "", _p, None), ("q", "", _q, None)], ("H", ""), mul(X(2), S("p"), S("q"), implicit=True), 2, None,
                 "So the frequency of heterozygotes is", style="request", drop=True, auto=("slip", "pow10", "round"))

formula_item("bio-rate-1", BIO, "physiology", "latex", "Oxygen production rose by 4.8 cm³ in 6.0 min. Calculate the mean rate of oxygen production.",
             [("V", "", "4.8", "cm3"), ("t", "", "6.0", "min")], ("r", ""), div(S("V"), S("t")), 2, "cm3/min", "The mean rate is therefore", sub_slip="t",
             misstate="V", wrong_unit="cm3")

# ================================================================================================ ESS
ESS = "Environmental Systems and Societies"
for _k, (_nota, _g, _r) in enumerate([("unicode", "2500", "1800"), ("ascii", "4200", "2900")]):
    formula_item(f"ess-npp-{_k + 1}", ESS, "productivity", _nota,
                 f"An ecosystem has a gross primary productivity of {_g} kJ m⁻² yr⁻¹ and respiratory losses of {_r} kJ m⁻² yr⁻¹. Calculate the net primary productivity.",
                 [("GPP", "", _g, "kJ/m2yr"), ("R", "", _r, "kJ/m2yr")], ("NPP", ""), minus(S("GPP"), S("R")), 2, "kJ/m2yr",
                 "The net primary productivity is therefore", sub_slip="R", auto=("slip", "sign")).unknown_units = True

for _k, (_nota, _n, _a) in enumerate([("unicode", "180", "12.0"), ("latex", "45", "2.5")]):
    formula_item(f"ess-density-{_k + 1}", ESS, "populations", _nota,
                 f"A survey counted {_n} plants in a {_a} m² area. Calculate the population density.",
                 [("N", "", _n, None), ("A", "", _a, "m2")], ("D", ""), div(S("N"), S("A")), 2, "/m2", "The population density is therefore", style="with",
                 sub_slip="A")

for _k, (_nota, _r) in enumerate([("unicode", "2.0"), ("ascii", "3.5")]):
    formula_item(f"ess-doubling-{_k + 1}", ESS, "populations", _nota,
                 f"A population grows at {_r} % per year. Estimate its doubling time using the rule of 70.",
                 [("r", "", _r, None)], ("t", "d"), div(X(70), S("r")), 2, "yr", "The doubling time is therefore about", style="request", auto=("slip", "pow10"))

# ======================================================================================= SEHS (sports)
SEHS = "Sports, Exercise and Health Science"
for _k, (_nota, _sv, _hr) in enumerate([("unicode", "70", "72"), ("latex", "95", "60"), ("ascii", "110", "150")]):
    formula_item(f"sehs-cardiac-{_k + 1}", SEHS, "cardiovascular", _nota,
                 f"An athlete has a stroke volume of {_sv} cm³ and a heart rate of {_hr} beats per minute. Calculate the cardiac output.",
                 [("SV", "", _sv, "cm3"), ("HR", "", _hr, "/min")], ("Q", ""), mul(S("SV"), S("HR")), 3, "cm3/min", "The cardiac output is therefore",
                 style="with", sub_slip="HR", wrong_unit="cm3")

for _k, (_nota, _m, _h) in enumerate([("unicode", "72", "1.80"), ("display", "58", "1.65")]):
    formula_item(f"sehs-bmi-{_k + 1}", SEHS, "body composition", _nota,
                 f"An athlete has a mass of {_m} kg and a height of {_h} m. Calculate the body mass index.",
                 [("m", "", _m, "kg"), ("h", "", _h, "m")], ("BMI", ""), div(S("m"), pw(S("h"), 2)), 3, "kg/m2", "The BMI is therefore", sub_slip="h",
                 misstate="m", wrong_unit="kg")

for _k, (_nota, _f, _d) in enumerate([("ascii", "250", "12"), ("latex", "40", "3.5")]):
    formula_item(f"sehs-work-{_k + 1}", SEHS, "biomechanics", _nota,
                 f"An athlete pushes a sled with a force of {_f} N through {_d} m. Calculate the work done.",
                 [("F", "", _f, "N"), ("d", "", _d, "m")], ("W", ""), mul(S("F"), S("d"), implicit=True), 2, "J", "The work done is therefore",
                 sub_slip="d", misstate="F", wrong_unit="N")

formula_item("sehs-speed-1", SEHS, "biomechanics", "unicode", "A sprinter runs 100 m in 10.4 s. Calculate the mean speed.",
             [("d", "", "100", "m"), ("t", "", "10.4", "s")], ("v", ""), div(S("d"), S("t")), 3, "m/s", "The mean speed is therefore", sub_slip="t",
             misstate="t", wrong_unit="m/s2")

# ================================================================================== DESIGN TECHNOLOGY
DT = "Design Technology"
for _k, (_nota, _f, _a) in enumerate([("unicode", "5000", "20"), ("latex", "1200", "8.0"), ("ascii", "750", "15")]):
    formula_item(f"dt-stress-{_k + 1}", DT, "materials", _nota,
                 f"A tie rod of cross-sectional area {_a} mm² carries a tensile load of {_f} N. Calculate the stress in the rod.",
                 [("F", "", _f, "N"), ("A", "", _a, "mm2")], ("σ", ""), div(S("F"), S("A")), 3, "N/mm2", "The stress is therefore", sub_slip="A",
                 misstate="F", wrong_unit="N")

for _k, (_nota, _dl, _l) in enumerate([("unicode", "0.60", "1500"), ("display", "2.4", "800")]):
    formula_item(f"dt-strain-{_k + 1}", DT, "materials", _nota,
                 f"A {_l} mm long specimen extends by {_dl} mm under load. Calculate the strain.",
                 [("ΔL", "", _dl, "mm"), ("L", "", _l, "mm")], ("ε", ""), div(S("ΔL"), S("L")), 2, None, "The strain is therefore", sub_slip="ΔL", sci=True,
                 auto=("slip", "pow10"))

for _k, (_nota, _ti, _to) in enumerate([("ascii", "60", "20"), ("unicode", "48", "16")]):
    formula_item(f"dt-gear-{_k + 1}", DT, "mechanisms", _nota,
                 f"A driven gear has {_ti} teeth and its driver gear has {_to} teeth. Calculate the velocity ratio.",
                 [("N", "driven", _ti, None), ("N", "driver", _to, None)], ("VR", ""), div(S("N", "driven"), S("N", "driver")), 2, None,
                 "The velocity ratio is therefore", style="with", sub_slip="N_driver", auto=("slip", "pow10"))

formula_item("dt-density-1", DT, "materials", "latex", "A component of volume 2.5 × 10⁻⁴ m³ is made of aluminium of density 2700 kg m⁻³. Calculate its mass.",
             [("ρ", "", "2700", "kg/m3"), ("V", "", "2.5e-4", "m3")], ("m", ""), mul(S("ρ"), S("V"), implicit=True), 2, "kg", "The mass is therefore",
             style="with", sub_slip="ρ", wrong_unit="kg/m3")

# hand-written items (algebra, roots, Boolean, tables, bases, equations, conversions, comparisons, targets)
import corpus_items_more  # noqa: E402,F401


# ============================================================================================ PROBES
# The 22 answers of the read-only probe of docs/STEM_DESIGN.md, section 1 (the same texts as
# tests/channel/test_stem_channel.py): 13 deliberately wrong answers that crossed the hub silently
# before STEM support, and 9 correct answers. Each wrong answer's fault is labelled with exact
# arithmetic in its note.
_PROBE_DATA = [
    ("P1-observed", "Physics", "A trolley accelerates uniformly from rest to 20 m s^-1 in 4.0 s. Calculate its acceleration.",
     "The trolley starts from rest, so u = 0. Using a = Δv/Δt, a = (20 - 0)/4.0 = 6.0 m s⁻². The acceleration is therefore 6.0 m s⁻².",
     ("arithmetic_slip", "(20 - 0)/4.0 = 6.0", ["INT-SUBJ-001"], ["eq"], "(20 - 0)/4.0 = 5 exactly; stated 6.0 [computed: |5 - 6| = 1 > 0.05 + 0.05]")),
    ("P2-latex-inline-ok", "Physics", "A stone is dropped from rest. Calculate its speed after 3.0 s.",
     "Taking $g = 9.8\\ \\text{m s}^{-2}$ and $u = 0$, we use $v = u + at$. So $v = 0 + 9.8 \\times 3.0 = 29.4\\ \\text{m s}^{-1}$.", None),
    ("P3-latex-display-err", "Physics", "Calculate the kinetic energy of a 2.0 kg mass moving at 3.0 m/s.",
     "The kinetic energy is given by\n\\[ E_k = \\frac{1}{2} m v^2 = \\frac{1}{2}(2.0)(3.0)^2 = 18\\,\\text{J} \\]\nThe mass therefore carries 18 J of kinetic energy.",
     ("dropped_factor", "\\frac{1}{2}(2.0)(3.0)^2 = 18", ["INT-SUBJ-001"], ["eq"], "½ × 2.0 × 3.0² = 9 exactly; stated 18 [computed: |9 - 18| = 9 > 0.5 + 0.09]")),
    ("P4-unicode-ok", "Physics", "Calculate the kinetic energy of a 2.0 kg mass moving at 3.0 m/s.", "Eₖ = ½mv² = ½ × 2.0 × 3.0² = 9.0 J. This is the energy the mass carries.", None),
    ("P5-sci-notation-err", "Physics", "Light of frequency 5.0 × 10^14 Hz travels in a vacuum. Determine its wavelength.",
     "The speed of light is c = 3.0 × 10^8 m/s (3.0e8 m s⁻¹). Using λ = c/f, λ = 3.0 × 10⁸ / 5.0 × 10¹⁴ = 6.0 × 10⁻⁶ m.",
     ("power_of_ten", "= 6.0 × 10⁻⁶ m", ["INT-SUBJ-001"], ["eq"], "3.0e8 / 5.0e14 = 6.0e-7; stated 6.0e-6 [computed: a factor of 10]")),
    ("P6-gravitation-ok", "Physics", "Calculate the gravitational force on a 70 kg person at the Earth's surface.",
     "F = Gm₁m₂/r² with G = 6.67 × 10⁻¹¹ N m² kg⁻², M = 5.97e24 kg and r = 6.37e6 m. F = 6.67 × 10⁻¹¹ × 5.97e24 × 70 / (6.37e6)² ≈ 687 N.", None),
    ("P7-momentum-err", "Physics", "Calculate the momentum of a 1200 kg car moving at 25 m/s.",
     "Momentum p = mv = 1200 kg × 25 m/s = 3.5 × 10⁴ kg·m/s. The car's momentum is 3.5 × 10⁴ kg m s⁻¹.",
     ("arithmetic_slip", "= 3.5 × 10⁴ kg·m/s", ["INT-SUBJ-001"], ["eq"], "1200 × 25 = 30000 exactly; stated 35000 [computed: |30000 - 35000| = 5000 > 500 + 300]")),
    ("P8-unit-conversion-err", "Physics", "Convert 72 km/h into m/s and state the time to travel 100 m.",
     "72 km h⁻¹ = 72 × 1000 / 3600 = 25 m s⁻¹. At 25 m/s, 100 m takes t = 100/25 = 4.0 s.",
     ("unit_conversion", "72 × 1000 / 3600 = 25", ["INT-SUBJ-001"], ["eq", "cnv"], "72 × 1000 / 3600 = 20 exactly; stated 25 [computed: |20 - 25| = 5 > 0.5]")),
    ("P9-sqrt-trig-ok", "Physics", "A ball falls 5.0 m. Calculate its speed, and the horizontal component of a 10 N force at 60° to the horizontal.",
     "v = √(2gh) = √(2 × 9.8 × 5.0) = 9.9 m/s. The horizontal component is F cos θ = 10 cos 60° = 5.0 N.", None),
    ("P10-percent-efficiency-err", "Physics", "A motor uses 500 J of electrical energy and does 400 J of useful work. Calculate its efficiency.",
     "Efficiency = useful output / input × 100% = 400 J / 500 J × 100% = 75%. The efficiency rose from 60 per cent to 75 per cent after servicing, a rise of 15 per cent.",
     [("arithmetic_slip", "= 75%", ["INT-SUBJ-001"], ["eq"], "400/500 × 100 = 80 exactly; stated 75 [computed: |80 - 75| = 5 > 0.5 + 0.8]"),
      ("prose_percent_change", "a rise of 15 per cent", ["INT-SUBJ-001"], [], "a rise from 60 to 75 is 25 per cent; stated 15 [computed: |25 - 15| = 10 > "
                                                                               "5 % of 25 + 0.5]")]),
    ("P11-units-misread-ok", "Physics", "Describe the change in length of the spring.",
     "The spring's length fell from 2 m to 50 cm, a fall of 75 per cent. The extension rose from 500 mm to 2 m, a fourfold increase.", None),
    ("P12-self-check-ok", "Physics", "Calculate the speed if d = 120 m and t = 8 s.", "v = d/t = 120 m / 8 s = 15 m/s. Check: 15 × 8 = 120, so the answer is verified and the units are correct.", None),
    ("C1-moles-err", "Chemistry", "Calculate the amount of water in 36 g of H₂O and the enthalpy change for burning 2 mol of hydrogen.",
     "n(H₂O) = m/M = 36 g ÷ 18.0 g mol⁻¹ = 3.0 mol. For 2 H₂ + O₂ → 2 H₂O, ΔH = 2 × (−286 kJ mol⁻¹) = −572 kJ.",
     ("arithmetic_slip", "= 3.0 mol", ["INT-SUBJ-001"], ["eq"], "36/18.0 = 2 exactly; stated 3.0 [computed: |2 - 3| = 1 > 0.05 + 0.02]")),
    ("C2-concentration-yield-err", "Chemistry", "Calculate the concentration and the percentage yield.",
     "c = n/V = 0.50 mol / 0.250 dm³ = 2.0 mol dm⁻³. The percentage yield is 4.5 g / 6.0 g × 100 = 80%.",
     ("arithmetic_slip", "× 100 = 80%", ["INT-SUBJ-001"], ["eq"], "4.5/6.0 × 100 = 75 exactly; stated 80 [computed: |75 - 80| = 5 > 0.5 + 0.75]")),
    ("C3-gas-law-ok", "Chemistry", "Calculate the volume of 0.50 mol of an ideal gas at 300 K and 100 kPa.",
     "Using pV = nRT, V = nRT/p = (0.50 × 8.31 × 300) / (100 × 10³) = 0.0125 m³ = 12.5 dm³.", None),
    ("M1-latex-quadratic-ok", "Mathematics: Analysis and Approaches", "Solve x^2 - 5x + 6 = 0.",
     "We solve $x^2 - 5x + 6 = 0$ with the quadratic formula: $x = \\frac{5 \\pm \\sqrt{25 - 24}}{2}$, so $x = 2$ or $x = 3$. Checking, $2^2 - 5(2) + 6 = 0$.", None),
    ("M2-series-err", "Mathematics AA HL", "Find the 10th term and the sum of the first 10 terms of the arithmetic sequence 3, 7, 11, ...",
     "Here $u_1 = 3$ and $d = 4$. Then $u_{10} = u_1 + 9d = 3 + 9 \\times 4 = 39$ and $S_{10} = \\frac{10}{2}(2(3) + 9(4)) = 220$.",
     ("arithmetic_slip", "= 220", ["INT-SUBJ-001"], ["eq"], "10/2 × (6 + 36) = 210 exactly; stated 220 [computed: exact work, 210 ≠ 220]")),
    ("M3-calculus-err", "Mathematics: Analysis and Approaches", "Differentiate f(x) = 3x^2 + 2x.",
     "Using the power rule, $f'(x) = \\frac{d}{dx}(3x^2 + 2x) = 3x + 2$. At $x = 1$, $f'(1) = 5$.",
     ("wrong_derivative", "f'(x) = \\frac{d}{dx}(3x^2 + 2x) = 3x + 2", ["INT-SUBJ-001"], ["alg"],
      "d/dx(3x² + 2x) = 6x + 2 by the power rule; stated 3x + 2 (STEM repair 11, rule derivative: decided; before, a derivative was outside "
      "the encodings and the relation was named undecided)")),
    ("M4-ai-percent-err", "Mathematics: Applications and Interpretation", "A price rose from 250 to 300. Calculate the percentage increase.",
     "The price rose from 250 to 300, a rise of 25 per cent. As a fraction, 50/250 = 0.2.",
     ("prose_percent_change", "a rise of 25 per cent", ["INT-SUBJ-001"], [], "(300 − 250)/250 = 20 per cent; stated 25 [computed: |25 - 20| = 5 > 5 % of 20 + 0.5]")),
    ("B1-magnification-err", "Biology", "Calculate the magnification of a cell whose image is 25 mm long and whose actual length is 50 µm.",
     "Magnification = image size / actual size = 25 mm / 50 µm = 25 000 µm / 50 µm = 50×.",
     ("arithmetic_slip", "25 mm / 50 µm = 25 000 µm / 50 µm = 50×", ["ST-PARSE-001"], [], "25 mm / 50 µm = 500; stated 50. '25 000' with a plain space is an ambiguous "
                                                                                       "numeral, so the relation is named unreadable (ST-PARSE-001)")),
    ("E1-ess-efficiency-ok", "Environmental Systems and Societies", "Calculate the efficiency of energy transfer between the trophic levels.",
     "Efficiency = 150 kJ m⁻² yr⁻¹ / 1500 kJ m⁻² yr⁻¹ × 100 = 10%. About 10% of the energy passes to the next level.", None),
    ("CS1-binary-err", "Computer Science", "Convert 1011 in binary to denary and FF in hexadecimal to denary.",
     "1011₂ = 1×2³ + 0×2² + 1×2¹ + 1×2⁰ = 11₁₀. FF₁₆ = 15 × 16 + 15 = 256.",
     ("arithmetic_slip", "15 × 16 + 15 = 256", ["INT-SUBJ-001"], ["eq", "base"], "15 × 16 + 15 = 255 exactly; stated 256")),
]
for _pid, _subj, _q, _resp, _fault in _PROBE_DATA:
    _faults = []
    for _cls, _step, _codes, _kinds, _note in ([] if _fault is None else _fault if isinstance(_fault, list) else [_fault]):
        _faults.append({"class": _cls, "step": _step, "expected_codes": _codes, "check_kinds": _kinds, "severity": "error" if _codes[0] == "INT-SUBJ-001" else "warning",
                        "note": _note, "proof": {"rule": "see note", "fails": True}})
    PROBES.append({"id": f"probe-{_pid}", "role": "mutant" if _faults else "correct", "parent": None, "source": "tests/channel/test_stem_channel.py (probe answers)",
                   "subject": _subj, "topic": "probe", "task_type": "short_answer", "question": _q, "supplied_texts": [], "response_text": _resp,
                   "notation": ["probe"], "gold": {"faults": _faults, "correct_steps": [], "affected_steps": [], "undecided": []}})
