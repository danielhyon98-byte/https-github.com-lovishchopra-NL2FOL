"""STEM repair 7: the seventh independent test of the STEM completion found three classes the front end did not decide as the pack
says. Each is fixed at its cause in the STEM front end, for its whole class, and every new reading has a clean control (correct
working is never flagged):

* rule ``solved-law``: a line that gives a symbol a value right after a law that states the symbol but not on its own ('ε = I(R + r)'
  then 'I = 12 V / 2.9 Ω = 4.1 A'; 'T½ = ln 2/λ, so λT½ = ln 2' then 'λ = 0.693/8.0 h = 0.087 h⁻¹'; 'V² = PR', 'F = ma', 'n = cV',
  'pV = nRT', 'E = ½mv²' …) was read as an algebra step from the law, decided exactly with the law's other symbols pinned to values
  from anywhere in the answer (R = 6.0 Ω from part (d)) and with rounded constants read as exact (0.693 for ln 2): correct working
  failed (INT-SUBJ-001). The line evaluates the law solved for the symbol: it is read exactly as the evaluation of that formula stated
  with the symbol alone ('I = ε/(R + r)', 'λ = ln 2/T½'), its substitution checked against it, and no step is read. A value alone after
  a law in the symbol alone (every other symbol given) is still its solution, a step within the value's band;
* rules ``leibniz`` and ``prime-derivative``: a derivative written with primes on any letter applied to a bracket ("v'(t)", 'v′(t)',
  "v'(1)", 's″(t)') or in Leibniz notation of any order and letters ('d²v/dt²', 'd^2y/dx^2', 'dN/dt', 'dθ/dt', '\\frac{d^2v}{dt^2}')
  was read as a product of symbols (v′·t, d²·v/(d·t²)), with neither a check nor an ST code, while D32 says ST-UNDEC-001 names a
  derivative; they are derivatives now: ST-UNDEC-001, and a derivative's value at a point is set against the answer's own formula of
  it ("v'(1) = 6 + 6(1)" after "v'(t) = 6 − 6t" fails);
* rule ``finer-restatement``: a value restated with a rounding finer than the chain's stated value ('To 3 s.f., V = 9.90 V.' or '…
  9.94 V.' after 'V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V', whose arithmetic gives 9.93) was set against the stated 9.9 V with h(S) +
  h(S′) and passed; beside that check, it is set against the chain's written arithmetic within the stated rounding, at warning
  severity (that the restated figures are the line's arithmetic as written is a reading).
"""
from __future__ import annotations

import pytest

from epinoic_logic.stem.lexer import lex
from epinoic_logic.stem.nodes import render
from epinoic_logic.stem.parser import _leibniz_end
from epinoic_logic.stem.relations import _solve_for

from .test_stem_repair5 import SPEC, PROFILE, after, clean, decide, failing, holds, new, replaced, task, warnings

#: anchors in the recorded r7 answers
PH_PART_B = "ε = I(R + r), so I = ε/(R + r)\nI = 12 V / 2.9 Ω = 4.1 A"
PH_PART_C = "V = ε − Ir\nV = 12 V − (4.14 A × 0.50 Ω) = 9.9 V"
PH_PART_D = "P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W"
PH_C = "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V"
PH_D = "= 16.4 W, so 16 W"
PB_PART_C = "T½ = ln 2/λ, so λ = ln 2/T½\nλ = 0.693/8.0 h = 0.087 h⁻¹"
PB_C = "λ = 0.693/8.0 h = 0.087 h⁻¹"
MA = "Distance travelled = 8 m  A1"
CH = "so I cannot give one yet."


def _steps(checks, text: str) -> list:
    """The algebra steps among ``checks`` whose statement quotes ``text``."""
    return [c for c in checks if c[0] == "alg" and f"the algebraic step: '{text}" in c[3]]


def _rule(checks, rule: str) -> list:
    return [c for c in checks if f"rule {rule}" in c[3]]


# ============================================================================================ rule solved-law
#: (task, the recorded working, the same working with the law written another way, the evaluation the step had been read to)
SOLVED_LAW_CONTROLS = [
    ("ph-t13", "ε = I(R + r), so I = ε/(R + r)", "ε = I(R + r)", "I = 12 V / 2.9 Ω"),
    ("ph-t13", PH_PART_B, "ε = I(R + r), so I = 12 V / 2.9 Ω = 4.1 A", "I = 12 V / 2.9 Ω"),
    ("ph-t13", PH_PART_B, "ε = I(R + r)\nI = 12 V / (2.4 Ω + 0.50 Ω) = 4.1 A", "I = 12 V / (2.4"),
    ("ph-t13", PH_PART_D, "V² = PR\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W", "P = (9.93 V)²"),
    ("ph-t13", PH_PART_C, "ε = V + Ir\n" + PH_C, "V = 12 V − (4.14"),
    ("ph-p7b", "T½ = ln 2/λ, so λ = ln 2/T½", "T½ = ln 2/λ, so λT½ = ln 2", "λ = 0.693/8.0 h"),
    ("ph-p7b", "T½ = ln 2/λ, so λ = ln 2/T½", "λT½ = ln 2", "λ = 0.693/8.0 h"),
]


@pytest.mark.parametrize("tid,old,new_text,evaluation", SOLVED_LAW_CONTROLS)
def test_the_evaluation_after_a_law_with_its_symbol_not_alone_is_no_step(tid, old, new_text, evaluation):
    """The tester's ph-t13 and ph-p7b controls and the other forms of the class: before, the evaluation was an exact algebra step from
    the law and failed (INT-SUBJ-001: r = 120/29 with R pinned to part (d)'s 6.0 Ω; r = 693/8000 with 0.693 read as exact). It is no
    step now, and nothing new fails or warns."""
    text = replaced(tid, old, new_text)
    checks, _f = task(tid, text)
    assert not _steps(checks, evaluation), _steps(checks, evaluation)
    clean(tid, text)


def test_the_evaluation_is_read_as_the_law_solved_for_its_symbol():
    """'λT½ = ln 2' then 'λ = 0.693/8.0 h' gets exactly the recorded answer's substitution check (the recorded working states 'λ = ln
    2/T½'), its statement naming rule solved-law and the formula it evaluates; '(2.4 Ω + 0.50 Ω)' is set against R's stated value."""
    text = replaced("ph-p7b", "T½ = ln 2/λ, so λ = ln 2/T½", "T½ = ln 2/λ, so λT½ = ln 2")
    subs = [c for c in task("ph-p7b", text)[0] if c[0] == "sub" and "'λ = 0.693/8.0 h'" in c[3]]
    assert len(subs) == 1 and holds(subs[0]) and "rule solved-law" in subs[0][3] and "λ = ln(2) / T_half" in subs[0][3], subs
    recorded = [c for c in task("ph-p7b", SPEC["ph-p7b"]["response_text"])[0] if c[0] == "sub" and "'λ = 0.693/8.0 h'" in c[3]]
    assert [c[1] for c in recorded] == [subs[0][1]] and "rule solved-law" not in recorded[0][3]
    sub = [c for c in new("ph-t13", replaced("ph-t13", PH_PART_B, "ε = I(R + r)\nI = 12 V / (2.4 Ω + 0.50 Ω) = 4.1 A"))[0] if c[0] == "sub"]
    assert len(sub) == 1 and holds(sub[0]) and "rule solved-law" in sub[0][3] and "substituted symbols: R" in sub[0][3], sub


@pytest.mark.parametrize("text", [
    "F = ma\na = 12 N / 3.0 kg = 4.0 m s⁻²",
    "n = cV\nc = 0.0050 mol ÷ 0.0550 dm³ = 0.091 mol dm⁻³",
    "P = IV\nI = 29 W / 10.7 V = 2.7 A",
    "v = fλ\nλ = 340 m s⁻¹ / 512 Hz = 0.664 m",
    "V² = PR\nP = (9.93 V)² / 6.0 Ω = 16.4 W",
    "pV = nRT\nT = (100000 Pa × 0.0010 m³) / (0.040 mol × 8.31 J mol⁻¹ K⁻¹) = 301 K",
    "ε = V + Ir\nV = 12 V − (4.1 A × 0.50 Ω) = 9.9 V",
    "Q = mcΔT\nΔT = 4200 J / (0.50 kg × 4200 J kg⁻¹ K⁻¹) = 2.0 K",
    "E = ½mv²\nv = √(2 × 50 J / 4.0 kg) = 5.0 m s⁻¹",
    "ε = I(R + r), so I = 12 V / 2.9 Ω = 4.1 A",
])
def test_a_law_then_its_evaluation_never_fails_correct_working(text):
    """Every one of these failed on the staged tree before the repair (the algebraic step, COUNTEREXAMPLE); no step is read now and
    every check holds."""
    checks, findings = decide(text, None, "physics")
    assert not [c for c in checks if c[0] == "alg"] and not failing(checks) and not warnings(findings), (checks, findings)


def test_faults_in_an_evaluation_of_a_solved_law_are_still_caught():
    """The rule hides no fault: an arithmetic slip fails its arithmetic; a half-life the answer does not state fails the substitution of
    the law solved for λ (and its stated roots); a wrong value alone after the law in λ alone fails as the step it still is; another
    resistor in the power line fails rule part-given (a warning), as after 'P = V²/R'; a concentration slip fails its arithmetic."""
    slip = new("ph-t13", replaced("ph-t13", PH_PART_B, "ε = I(R + r)\nI = 12 V / (2.4 Ω + 0.50 Ω) = 4.8 A"))[0]
    assert [c[0] for c in failing(slip) if "4.8 A" in c[3]] == ["eq"]
    given = new("ph-p7b", replaced("ph-p7b", PB_PART_C, "T½ = ln 2/λ, so λT½ = ln 2\nλ = 0.693/9.0 h = 0.077 h⁻¹"))[0]
    bad = failing(given)
    assert sorted(c[0] for c in bad) == ["sol", "sub"] and _rule(bad, "solved-law") == [c for c in bad if c[0] == "sub"], bad
    alone = new("ph-p7b", replaced("ph-p7b", PB_PART_C, "T½ = ln 2/λ, so λT½ = ln 2\nλ = 0.097 h⁻¹"))[0]
    assert {c[0] for c in failing(alone)} == {"alg", "sol"}
    alone_ok = new("ph-p7b", replaced("ph-p7b", PB_PART_C, "T½ = ln 2/λ, so λT½ = ln 2\nλ = 0.087 h⁻¹"))[0]
    assert not failing(alone_ok) and _steps(alone_ok, "λ = 0.087 h⁻¹")
    part = new("ph-t13", replaced("ph-t13", PH_PART_D, "V² = PR\nP = (9.93 V)² / 4.0 Ω = 24.7 W, so 25 W"))[0]
    assert [(c[0], c[2]) for c in failing(part)] == [("sub", "warning")] and "rule part-given" in failing(part)[0][3]
    chem, _f = task("ch-t13", after("ch-t13", CH, "n = cV\nc = 0.0050 mol ÷ 0.0550 dm³ = 0.91 mol dm⁻³", "\n\n"))
    assert [c[0] for c in failing(chem)] == ["eq"]


def test_a_wrong_value_for_a_symbol_substituted_before_is_still_caught():
    """'ω = 2πf so f = 3.0/(2π)' after '2π/ω = 2π/4.0': ω has no stated value, only the 4.0 substituted before; the algebra step had
    pinned ω to it and failed, and the solved law's substitution sets ω's 3.0 against it and fails (its statement saying so)."""
    checks, _f = decide("T = 2π/ω = 2π/4.0 = 1.57 s and ω = 2πf so f = 3.0/(2π) = 0.48 Hz", None, "physics")
    bad = failing(checks)
    assert [c[0] for c in bad] == ["sub"] and "rule solved-law: ω has no stated value" in bad[0][3], bad
    ok, _f = decide("T = 2π/ω = 2π/4.0 = 1.57 s and ω = 2πf so f = 4.0/(2π) = 0.64 Hz", None, "physics")
    assert ok and not failing(ok)


def test_an_equation_in_the_symbol_alone_is_read_as_before():
    """Not read by rule solved-law: an equation with no other symbol. Its solution is still the algebra step it was ('2x + 3 = 11' then
    'x = (11 − 3)/2') and a quadratic's stated root is still checked against it; both hold, and a wrong solution still fails."""
    checks, _f = decide("2x + 3 = 11\nx = (11 − 3)/2 = 4", None, "mathematics_aa")
    assert _steps(checks, "x = (11 − 3)/2") and not failing(checks) and not _rule(checks, "solved-law"), checks
    checks, _f = decide("x² − 5x + 6 = 0\nx = (5 + 1)/2 = 3", None, "mathematics_aa")
    assert [c[0] for c in checks if c[0] == "sol"] == ["sol"] and not failing(checks) and not _rule(checks, "solved-law"), checks
    bad, _f = decide("2x + 3 = 11\nx = (11 + 3)/2 = 7", None, "mathematics_aa")
    assert [c[0] for c in failing(bad)] == ["alg"]


def test_in_mathematics_a_squared_symbol_s_evaluation_names_its_principal_root():
    """'A = πr²' then 'r = √(50/π)' (A = 50 stated) evaluates the law solved for r, its substitution holding (as an algebra step it was
    decided with A pinned, and failed when A had no stated value); solving took the principal root, which ST-ALG-001 still names when no
    domain restriction is stated, as for the step it replaces; with 'r > 0' stated, no finding."""
    checks, findings = decide("A = 50\nA = πr²\nr = √(50/π) = 3.99", None, "mathematics_aa")
    sub = _rule(checks, "solved-law")
    assert [c[0] for c in sub] == ["sub"] and holds(sub[0]) and not _steps(checks, "r = √(50/π)") and not failing(checks), checks
    assert [f[0] for f in warnings(findings)] == ["ST-ALG-001"] and "rule solved-law" in warnings(findings)[0][2], findings
    checks, findings = decide("A = πr²\nr = √(50/π) = 3.99", None, "mathematics_aa")
    assert not failing(checks) and [f[0] for f in warnings(findings)] == ["ST-ALG-001"], (checks, findings)
    checks, findings = decide("A = πr²\nr = √(50/π) = 3.99", None, "physics")
    assert not failing(checks) and not warnings(findings), (checks, findings)


def test_a_given_statement_after_a_law_is_data_never_a_step():
    """A Given statement states data, never the evaluation of the law before it nor a step from it: 'Given: ε = 12 V.' right after 'I =
    ε/(R + r)' had been read as an algebra step from the law (with I, R and r pinned) and failed; it is checked against the request as
    a Given (the request states the emf, 12 V), and a contradicting Given still fails that check, at warning severity."""
    text = replaced("ph-t13", PH_PART_B, "I = ε/(R + r)\nGiven: ε = 12 V.\nI = 12 V / 2.9 Ω = 4.1 A")
    checks, _f = task("ph-t13", text)
    assert not _rule(checks, "solved-law") and not _steps(checks, "ε = 12 V") and not failing(checks)
    assert [c for c in checks if c[0] == "giv" and holds(c)], checks
    bad, _f = task("ph-t13", replaced("ph-t13", PH_PART_B, "I = ε/(R + r)\nGiven: ε = 15 V.\nI = 15 V / 2.9 Ω = 5.2 A"))
    assert [(c[0], c[2]) for c in failing(bad) if "15 V" in c[3].split(" [claims")[0]] == [("giv", "warning")], failing(bad)


@pytest.mark.parametrize("law,name,solved", [
    ("ε = I(R + r)", "I", "ε / (R + r)"),
    ("λT½ = ln 2", "λ", "ln(2) / T_half"),
    ("V² = PR", "P", "V^2 / R"),
    ("1/R = 1/R₁ + 1/R₂", "R", "1 / (1 / R_1 + 1 / R_2)"),
    ("ε = V + Ir", "V", "ε - I·r"),
    ("V = ε − Ir", "I", "(ε - V) / r"),
    ("E = ½mv²", "v", "sqrt(E / ½ / m)"),
])
def test_a_law_solved_for_a_symbol_is_the_law_rearranged(law, name, solved):
    """The solved formula is the stated law rearranged by exact inverse operations, nothing else."""
    from epinoic_logic.stem import build_document
    doc = build_document(law, None, "physics")
    rel = next(r for r in doc.relations if r.left is not None and r.right is not None)
    got = _solve_for(rel.left.readings[0], rel.right.readings[0], name, roots=True)
    assert got is not None and render(got) == solved, (law, render(got) if got is not None else None)


@pytest.mark.parametrize("law,name", [("s = ut + ½at²", "t"), ("N = N₀e^(−λt)", "t"), ("v = u + at", "w")])
def test_a_symbol_twice_or_under_a_function_is_never_isolated(law, name):
    from epinoic_logic.stem import build_document
    doc = build_document(law, None, "physics")
    rel = next(r for r in doc.relations if r.left is not None and r.right is not None)
    assert _solve_for(rel.left.readings[0], rel.right.readings[0], name, roots=True) is None


# ============================================================================================ rules leibniz and prime-derivative
#: STEM repair 11 (rule derivative): the derivatives of a letter the text gives no function of stay named unchecked
UNDEFINED_DERIVATIVES = ["    Also θ′(t) = 2", "    Also dN/dt = −2N", "    Also dθ/dt = 2", "    Also $\\frac{dN}{dt} = -2N$", "    Also $\\frac{d\\theta}{dt} = 2$"]
#: STEM repair 11 (rule derivative): the derivatives of the answer's v = 6t − 3t² (or of the expression written out), right and wrong
RIGHT_DERIVATIVES = ["    Also v′(t) = 6 − 6t", "    So v″(t) = −6", "    Also d²v/dt² = −6", "    Also d²/dt²(6t − 3t²) = −6", "    Also $\\frac{d^2v}{dt^2} = -6$"]
WRONG_DERIVATIVES = ["    Also v'(t) = 6 + 6t", "    Since v = 6t − 3t², v'(t) = 6 + 6t", "    Also d²v/dt² = 6", "    Also d^2v/dt^2 = 6",
                     "    Also d^{2}v/dt^{2} = 6", "    v'(1) = 6 + 6(1) = 12"]
#: the sixteen notations of the repair-7 test, every one still read as a derivative
DERIVATIVES = UNDEFINED_DERIVATIVES + RIGHT_DERIVATIVES + WRONG_DERIVATIVES


@pytest.mark.parametrize("line", UNDEFINED_DERIVATIVES)
def test_every_notation_of_a_derivative_is_named_unchecked(line):
    """Before, each was read as a product of symbols with neither a check nor an ST code (only "dv/dt", "d/dx" and f′, g′, h′ were
    derivatives): each is named ST-UNDEC-001 'a derivative' now, and never failed (a derivative's arithmetic is still checked). STEM repair
    11: this holds for the derivative of a letter the text gives no function of; the derivatives of the answer's own v(t) are checked (the
    two tests below)."""
    checks, findings = new("maa-t13", after("maa-t13", MA, line))
    assert [f[0] for f in warnings(findings)] == ["ST-UNDEC-001"] and "a derivative" in warnings(findings)[0][2], findings
    assert not failing(checks), checks


@pytest.mark.parametrize("line", RIGHT_DERIVATIVES)
def test_every_notation_of_a_right_derivative_of_the_answer_s_function_holds(line):
    """STEM repair 11 (rule derivative): before, named ST-UNDEC-001 'a derivative' (the previous test); each is set against the derivative
    the STEM pack forms by the power rule from the answer's v = 6t − 3t² now, and holds, with no ST code left."""
    checks, findings = new("maa-t13", after("maa-t13", MA, line))
    der = [c for c in checks if "the derivative formed by the power rule" in c[3]]
    assert len(der) == 1 and not failing(checks) and not warnings(findings), (checks, findings)


@pytest.mark.parametrize("line", WRONG_DERIVATIVES)
def test_every_notation_of_a_wrong_derivative_of_the_answer_s_function_fails(line):
    """STEM repair 11 (rule derivative): before, named ST-UNDEC-001 and never failed; each is set against the power rule's derivative of the
    answer's v = 6t − 3t² now and fails as an error on its own claim (a wrong value of v′ at a point, against the derivative there)."""
    checks, findings = new("maa-t13", after("maa-t13", MA, line))
    bad = failing(checks)
    assert len(bad) == 1 and bad[0][2] == "error" and "the derivative formed by the power rule" in bad[0][3] and not warnings(findings), \
        (checks, findings)


def test_a_derivative_s_value_is_set_against_the_answer_s_own_formula_of_it():
    """"v'(1)" after the answer's "v'(t) = 6 − 6t" is that formula at t = 1: '6 + 6(1)' fails it, '6 − 6(1)' holds (the formula itself
    is named unchecked: differentiation is outside the encodings). STEM repair 11 (rule derivative): the formula itself is checked by the
    power rule now, and holds."""
    bad, f = new("maa-t13", after("maa-t13", MA, "    Also v'(t) = 6 − 6t\n    v'(1) = 6 + 6(1) = 12"))
    wrong = failing(bad)
    # exactly one failed check: the derivative's value against the answer's own formula, quoting the line and naming both claims
    assert [(c[0], c[1], c[2]) for c in wrong] == [("eq", "COUNTEREXAMPLE", "error")], wrong
    assert "'v'(1) = 6 + 6(1)' [claims s3.12, s3.11]" in wrong[0][3], wrong
    formula = [c for c in bad if "the derivative formed by the power rule" in c[3]]
    assert len(formula) == 1 and holds(formula[0]) and "'v'(t) = 6 − 6t'" in formula[0][3] and not warnings(f), (bad, f)
    ok, f2 = new("maa-t13", after("maa-t13", MA, "    Also v'(t) = 6 − 6t\n    v'(1) = 6 − 6(1) = 0"))
    assert ok and not failing(ok) and not warnings(f2)


@pytest.mark.parametrize("text", ["d²v/dt = 6", "speed = d/t = 12", "v' = 2.0 m s⁻¹", "v′ (t) = 2"])
def test_what_is_no_derivative_is_read_as_before(text):
    """Orders that differ ('d²v/dt'), a distance over a time ('d/t'), a primed symbol with no bracket (v′ after a collision) and a primed
    symbol spaced off its bracket are no derivative notation: none is named 'a derivative'."""
    _checks, findings = decide(text, None, "physics")
    assert not [f for f in findings if "a derivative" in f[2]], findings


@pytest.mark.parametrize("text,end", [
    ("dv/dt", 3), ("dN/dt", 3), ("dθ/dt", 4), ("d²v/dt²", 6), ("d^2y/dx^2", 8), ("d2y/dx2", 6), ("d/dx", 3), ("d²/dx²", 5),
])
def test_leibniz_forms_end_after_their_denominator(text, end):
    toks = lex(text).tokens
    assert _leibniz_end(toks, 0) == end == len(toks)


@pytest.mark.parametrize("text", ["d²v/dt", "dv/dt²", "d/t", "dv/d", "d v/dt"])
def test_leibniz_forms_need_matching_orders_and_a_differential(text):
    assert _leibniz_end(lex(text).tokens, 0) is None


# ============================================================================================ rule finer-restatement
FINER = [
    # (where, the plant, its control)
    (PH_C, "\nTo 3 s.f., V = 9.90 V.", "\nTo 3 s.f., V = 9.93 V."),
    (PH_C, "\nTo three significant figures, V = 9.94 V.", "\nTo three significant figures, V = 9.93 V."),
    (PH_C, "\nV = 9.94 V (3 s.f.).", "\nV = 9.93 V (3 s.f.)."),
    (PH_C, ", so 9.95 V to 3 s.f.", ", so 9.93 V to 3 s.f."),
    (PH_C, "\nTo 3 s.f., the terminal potential difference is 9.94 V.", "\nTo 3 s.f., the terminal potential difference is 9.93 V."),
    (PH_C, "\nTo 3 s.f., V = 9900 mV.", "\nTo 3 s.f., V = 9930 mV."),
    (PH_C, "\nTo 2 d.p., V = 9.95 V.", "\nTo 2 d.p., V = 9.93 V."),
    (PH_D, "\nTo 4 s.f., P = 16.34 W.", "\nTo 4 s.f., P = 16.43 W."),
]


@pytest.mark.parametrize("anchor,plant,control", FINER)
def test_a_restatement_finer_than_the_chain_s_value_is_set_against_its_arithmetic(anchor, plant, control):
    """Before, each plant was set against the chain's stated value with both half-widths and held. Now a check of rule
    finer-restatement sets it against the chain's written arithmetic within the stated rounding and fails at warning severity (an
    error too when the plant also contradicts the stated value); the control's checks all hold."""
    checks, _f = new("ph-t13", replaced("ph-t13", anchor, anchor + plant))
    finer = _rule(checks, "finer-restatement")
    assert len(finer) == 1 and not holds(finer[0]) and finer[0][2] == "warning", checks
    ok, f = new("ph-t13", replaced("ph-t13", anchor, anchor + control))
    assert len(_rule(ok, "finer-restatement")) == 1 and not failing(ok) and not warnings(f), (ok, f)


def test_the_finer_check_reads_a_written_constant_over_its_interval_and_a_stated_value_check_stays():
    """After 'λ = 0.693/8.0 h = 0.087 h⁻¹': 'To 3 s.f., λ = 0.0866 h⁻¹.' holds both checks, '0.0867 h⁻¹' fails the finer check only;
    the rounding-cue check against the stated 0.087 h⁻¹ stays as it was (no check is weakened)."""
    ok, _f = new("ph-p7b", replaced("ph-p7b", PB_C, PB_C + "\nTo 3 s.f., λ = 0.0866 h⁻¹."))
    assert not failing(ok) and len(_rule(ok, "finer-restatement")) == 1 and len(_rule(ok, "rounding-cue")) == 0
    res = [c for c in ok if c[0] == "res"]
    assert len(res) == 2 and all(holds(c) for c in res)
    bad, _f = new("ph-p7b", replaced("ph-p7b", PB_C, PB_C + "\nTo 3 s.f., λ = 0.0867 h⁻¹."))
    assert [c for c in failing(bad)] == _rule(bad, "finer-restatement") and len(failing(bad)) == 1


@pytest.mark.parametrize("anchor,line", [
    (PH_C, "\nTo 2 s.f., V = 9.9 V."), (PH_C, "\nTo 1 d.p., V = 9.9 V."), (PH_D, "\nTo 1 s.f., P = 20 W."), (PH_C, "\nTo 2 s.f., V = 9.8 V."),
])
def test_a_restatement_no_finer_than_the_chain_s_value_gets_no_finer_check(anchor, line):
    checks, _f = new("ph-t13", replaced("ph-t13", anchor, anchor + line))
    assert not _rule(checks, "finer-restatement") and [c for c in checks if c[0] == "res"], checks


def test_no_recorded_round_7_answer_gets_a_reading_of_this_repair():
    """The recorded STEM answers state no law then evaluate another of its symbols, no other derivative notation and no finer
    restatement: none of their checks names a rule of this repair (the front end's dump of them is byte for byte as before)."""
    for tid, spec in SPEC.items():
        if tid not in PROFILE:
            continue
        checks, findings = task(tid, spec["response_text"])
        assert not [c for c in checks if "rule solved-law" in c[3] or "rule finer-restatement" in c[3]], tid
        assert sum("a derivative" in f[2] for f in findings) == (1 if tid == "maa-t13" else 0), (tid, findings)
