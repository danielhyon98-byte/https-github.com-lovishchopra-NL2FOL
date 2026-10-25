"""No false errors (docs/STEM_DESIGN.md, sections 1 and 16): correct work written the way STEM
specialists write it must never yield a failed check. Each answer below is correct; every check
built for it must hold when the engine decides it (and at least one check must be built, so a
pass is never vacuous).

Classes: rounding to the written precision; booklet constants (9.8 against 9.81, 6.6 against
6.63 × 10⁻³⁴); carried intermediates (4.85 → 4.9, ≈ 5); approximate chains; conversions inside
chains; bare conversion factors (÷ 3.6); percentages both ways; physics positive roots; sign
conventions (g = −9.81); part (b) reusing part (a)'s letters; and a few more shapes that agents
produce (commuted substitutions, exact surds, enclosures, ambiguous unit symbols, temperatures)."""
from __future__ import annotations

from typing import Optional

import pytest

from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.runner import verify
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem import build_document
from epinoic_logic.stem.checks import build_checks

CFG = SolverConfig(timeout_ms=10000, memory_max_mb=None)

CORRECT: list[tuple[str, str, Optional[str], str]] = [
    # (name, answer, request, profile)
    # rounding to the written precision
    ("round-1", "v = u + at = 0 + 9.8 × 3.0 = 29.4 m s⁻¹ ≈ 29 m s⁻¹", None, "physics"),
    ("round-2", "1/3 = 0.333 and 2/3 = 0.67 and 22/7 = 3.14", None, "mathematics_aa"),
    ("round-3", "√2 = 1.41 and π ≈ 3.14", None, "mathematics_aa"),
    ("round-4", "a = 2.0 / 0.41 = 4.878 ≈ 4.9 m s⁻²", None, "physics"),
    ("round-5", "F = 1200 × 1.7 = 2040 N ≈ 2.0 × 10³ N", None, "physics"),
    ("round-6", "I = 0.90 / 1.60*10**-19 = 5.6*10**18", None, "physics"),
    # booklet constants
    ("booklet-g", "The weight is W = mg = 40 × 9.8 = 392 N.", "A 40 kg box rests on the floor. Take g = 9.81 m s⁻².", "physics"),
    ("booklet-g-unit", "W = 12 kg × 9.81 m/s² = 117.72 kg·m/s² = 117.72 N ≈ 118 N", None, "physics"),
    ("booklet-h", "E = hf = 6.6 × 10⁻³⁴ × 5.0 × 10¹⁴ = 3.3 × 10⁻¹⁹ J.", "Light of frequency 5.0 × 10¹⁴ Hz. Take h = 6.63 × 10⁻³⁴ J s.", "physics"),
    ("booklet-h-unstated", "E = hf = 3.3 × 10⁻¹⁹ J with f = 5.0 × 10¹⁴ Hz.", None, "physics"),
    ("booklet-c", "λ = c/f = 3.00 × 10⁸ / 5.0 × 10¹⁴ = 6.0 × 10⁻⁷ m", None, "physics"),
    ("booklet-NA", "n = N/N_A = 1.204 × 10²⁴ / 6.02 × 10²³ = 2.00 mol", None, "chemistry"),
    # carried intermediates
    ("carried-4.9", "a = 9.7/2.0 = 4.85 m s⁻² ≈ 4.9 m s⁻². So F = ma = 3.0 × 4.9 = 14.6 N.", None, "physics"),
    ("carried-5", "a = 9.7/2.0 = 4.85 m s⁻² ≈ 5 m s⁻². So F = ma = 3.0 × 5 = 14.6 N.", None, "physics"),
    ("carried-unit", "v = 200 km ÷ 3 h = 67 km h⁻¹.\nv = 67 km h⁻¹ ÷ 3.6 = 18.6 m s⁻¹ ≈ 19 m s⁻¹", None, "physics"),
    # approximate chains
    ("approx-1", "s = ½ × 9.81 × 3.0² ≈ 44 m", None, "physics"),
    ("approx-2", "The distance is about 2.0 × 21 = 44 m.", None, "physics"),
    ("approx-3", "F = 6.67e-11 × 5.97e24 × 70 / (6.37e6)^2 ≈ 687 N", None, "physics"),
    # conversions inside chains
    ("cnv-chain", "V = nRT/p = 0.50 × 8.31 × 300 / 100000 = 0.0125 m³ = 12.5 dm³", None, "physics"),
    ("cnv-mass", "m = 58 g = 0.058 kg and Δt = 4.0 ms = 4.0 x 10^-3 s", None, "physics"),
    ("cnv-energy", "1 eV = 1.60 × 10⁻¹⁹ J, so 28.3 MeV = 28.3 × 10⁶ × 1.60 × 10⁻¹⁹ = 4.53 × 10⁻¹² J", None, "physics"),
    ("cnv-volume", "4500 cm³ min⁻¹ = 4.5 dm³ min⁻¹ since 1 dm³ = 1000 cm³", None, "biology"),
    # bare conversion factors
    ("factor-3.6", "v = 72 km h⁻¹ ÷ 3.6 = 20 m s⁻¹", None, "physics"),
    ("factor-1000", "v = 72 km h⁻¹ = 72 × 1000 m ÷ 3600 s = 20 m s⁻¹", None, "physics"),
    # percentages both ways
    ("pct-1", "The efficiency is 4.5/6.0 × 100 = 75 %.", None, "physics"),
    ("pct-2", "The fraction is 0.75 = 75 %.", None, "physics"),
    ("pct-3", "Efficiency = P_out/P_in × 100% = 588/750 × 100% = 78.4% ≈ 78%", None, "physics"),
    ("pct-4", "Percentage change = (2.35 − 2.50)/2.50 × 100 = −6.0%", None, "biology"),
    ("pct-5", "So 2pq = 2 × 0.6 × 0.4 = 0.48. Therefore 48% of the population are carriers.", None, "biology"),
    # physics positive roots
    ("root-1", "s = ½gt² so t² = 2s/g, giving t = √(2s/g).", None, "physics"),
    ("root-2", "The time is t = √(2s/g) = √(2 × 45.0 / 9.81) = 3.03 s.", None, "physics"),
    ("root-3", "v² = 2gh ⇒ v = √(2gh)", None, "physics"),
    # sign conventions
    ("sign-1", "Using g = −9.81 m s⁻², v = u + at = 0 + (−9.81)(2.0) = −19.6 m s⁻¹.", None, "physics"),
    ("sign-2", "a = −9.8 m s⁻², so F = ma = 2.0 × (−9.8) = −19.6 N", None, "physics"),
    ("sign-3", "p = m₁u₁ + m₂u₂ = 2.0 × 3.0 + 1.0 × (−4.0) = 2.0 kg m s⁻¹", None, "physics"),
    # part (b) reusing part (a)'s letters
    ("parts", "(a) v = 3.0 m s⁻¹, so KE = ½ × 2.0 × 3.0² = 9.0 J.\n\n(b) v = 4.0 m s⁻¹, so KE = ½ × 2.0 × 4.0² = 16 J.", None, "physics"),
    ("parts-sub", "Ek = ½mv² = ½ · 1500 · 12² = 1.08 × 10⁵ J.\n\nAt the higher speed, Ek = ½ · 1500 · 20² = 3.0 × 10⁵ J.", None, "physics"),
    # commuted substitutions
    ("commuted", "Given: m = 5.0 kg and g = 9.81 m s⁻².\nW = mg = 9.81 × 5.0 = 49.1 N", None, "physics"),
    # exact work, surds and enclosures
    ("exact", "640 × ½³ = 640/8 = 80 and ½³ = 1/8 = 0.125", None, "physics"),
    ("surds", "√8 + √18 = 2√2 + 3√2 = 5√2 ≈ 7.07", None, "mathematics_aa"),
    ("rationalise", "2/(√3 − 1) = 2(√3 + 1)/((√3 − 1)(√3 + 1)) = 2(√3 + 1)/(3 − 1) = √3 + 1", None, "mathematics_aa"),
    ("trig", "The components are 10 × sin 30° = 5.0 N and 10 × cos 30° = 8.66 N and 10 × sin 25° = 4.23 N.", None, "physics"),
    ("logs", "x = ln 50 / ln 2 = 3.912/0.6931 = 5.64, log₂ 32 = 5 and log 1000 = 3", None, "mathematics_aa"),
    ("pH", "pH = −log[H⁺] = −log(0.020) = 1.70", None, "chemistry"),
    ("omega", "ω = 2π/T = 2π/0.50 = 4π ≈ 12.6 rad s⁻¹", None, "physics"),
    # units read two ways, temperatures
    ("ms-1", "v = 72 × 1000 m ÷ 3600 s = 20 ms⁻¹", None, "physics"),
    ("celsius", "T = 25 °C = 298 K and ΔT = 40 °C − 20 °C = 20 K", None, "physics"),
    ("rise", "The temperature rise is ΔT = 20 °C = 20 K.", None, "physics"),
    ("unknown-unit", "Efficiency = 150 kJ m⁻² yr⁻¹ / 1500 kJ m⁻² yr⁻¹ × 100 = 10%", None, "ess"),
    # algebra, roots, inequalities, chemistry, Boolean
    ("algebra", "y(x + 1) = 3x − 2\nxy + y = 3x − 2\nxy − 3x = −2 − y\nx(y − 3) = −2 − y\nx = (−2 − y)/(y − 3)", None, "mathematics_aa"),
    ("quadratic", "x² − 5x + 6 = 0\n(x − 2)(x − 3) = 0\nx = 2 or x = 3", None, "mathematics_aa"),
    ("roots-decimal", "x² = 2 ⇒ x = 1.41 or x = −1.41", None, "mathematics_aa"),
    ("roots-exact", "Here a = 2, b = −3 and c = −1.\nDiscriminant: Δ = b² − 4ac = (−3)² − 4(2)(−1) = 9 + 8 = 17\nx = (−b ± √Δ)/(2a) = (3 ± √17)/4\n\n"
                    "So x = (3 + √17)/4 ≈ 1.78 or x = (3 − √17)/4 ≈ −0.281.", "Solve 2x² − 3x − 1 = 0.", "mathematics_aa"),
    ("algebra-latex", "\\begin{align*}\ny(x + 1) &= 3x - 2 \\\\\nxy + y &= 3x - 2 \\\\\nxy - 3x &= -2 - y \\\\\nx(y - 3) &= -2 - y \\\\\n"
                      "x &= \\frac{-2 - y}{y - 3} = \\frac{y + 2}{3 - y}\n\\end{align*}", None, "mathematics_aa"),
    ("inequality", "3 − 2x > 7\n−2x > 4\nx < −2", None, "mathematics_aa"),
    ("balance", "CH₄ + 2O₂ → CO₂ + 2H₂O and Fe³⁺ + e⁻ → Fe²⁺", None, "chemistry"),
    ("boolean", "A ∨ (A ∧ B) = A and ¬(A ∨ B) = ¬A ∧ ¬B", None, "computer_science"),
    ("based", "FF₁₆ = 255 and 1010₂ = 10 and 0x1F = 31", None, "computer_science"),
    ("given-target", "Given: m = 2.0 kg, v = 3.0 m s⁻¹.\nKE = ½mv² = ½ × 2.0 × 3.0² = 9.0 J.",
     "A 2.0 kg ball moves at 3.0 m s⁻¹. Show that its kinetic energy is about 9 J.", "physics"),
    ("restated", "I = V/R = 12/2.4 = 5.0 A. The current is therefore 5.0 A.", None, "physics"),
    # a step that substitutes a value read from an earlier substitution
    ("step-substitutes", "T = 2π/ω = 2π/4.0 = 1.57 s and ω = 2πf so f = 4.0/(2π) = 0.64 Hz", None, "physics"),
    # LaTeX inline, display and aligned derivations
    ("latex-inline", "The kinetic energy is $E_k = \\frac{1}{2}mv^2 = \\frac{1}{2}(0.40)(5.0)^2 = 5.0\\,\\text{J}$.", None, "physics"),
    ("latex-display", "$$s = ut + \\tfrac{1}{2}at^2 = (2.0)(4.0) + \\tfrac{1}{2}(1.5)(4.0)^2 = 8.0 + 12 = 20\\,\\text{m}$$", None, "physics"),
    ("latex-align", "\\begin{align*}\nF &= ma \\\\\n  &= 1500 \\times 2.0 \\\\\n  &= 3000\\,\\text{N} \\\\\n  &= 3.0\\,\\text{kN}\n\\end{align*}", None, "physics"),
    ("continued-lines", "The impulse is\nF Δt = Δp\n= 0.15 × (12 − (−8.0))\n= 0.15 × 20\n= 3.0 N s", None, "physics"),
    ("parallel", "Given: R₁ = 4.0 Ω, R₂ = 6.0 Ω.\nSeries: R = R₁ + R₂ = 4.0 + 6.0 = 10 Ω.\nParallel: 1/R = 1/R₁ + 1/R₂ = 1/4.0 + 1/6.0 = 0.417 Ω⁻¹, so R = 2.4 Ω.",
     None, "physics"),
    ("equilibrium", "Kc = [NH₃]²/([N₂][H₂]³) = (0.20)²/((0.50)(0.30)³) = 0.04/0.0135 = 2.96", None, "chemistry"),
    ("surd-product", "$(2 + \\sqrt{3})(2 - \\sqrt{3}) = 4 - 3 = 1$", None, "mathematics_aa"),
    ("degrees-latex", "$\\cos 60^\\circ = 0.5$ and $\\tan 45^\\circ = 1$ and $\\sin 90^\\circ = 1$", None, "mathematics_aa"),
    ("photoelectric", "E_k = hf − φ = 6.63 × 10⁻³⁴ × 1.0 × 10¹⁵ − 3.0 × 10⁻¹⁹ = 3.6 × 10⁻¹⁹ J.", None, "physics"),
    ("hardy-weinberg", "q² = 0.09 so q = 0.3 and p = 1 − q = 0.7; 2pq = 2 × 0.7 × 0.3 = 0.42.", None, "biology"),
    ("cardiac", "Cardiac output = 70 cm³ × 72 min⁻¹ = 5040 cm³ min⁻¹ ≈ 5.0 dm³ min⁻¹", None, "sports_science"),
    ("tonne", "The mass is 2.5 t = 2500 kg.", None, "design_technology"),
    ("based-sum", "1011₂ = 8 + 2 + 1 = 11 and 0x2A = 42 and 377₈ = 255", None, "computer_science"),
]


def _decide(pc):
    res = verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy))
    ok = res.status.value == pc.expected_if_sound and not any(d.code == "E108" for d in res.diagnostics)
    return ok, res


@pytest.mark.parametrize("name,text,req,profile", CORRECT, ids=[c[0] for c in CORRECT])
def test_correct_work_never_fails(name, text, req, profile):
    doc = build_document(text, req, profile)
    plan = build_checks(doc, report_id="r1", request_id="q1")
    assert plan.checks, (name, plan.findings, [r.kind for r in doc.relations])
    for pc in plan.checks:
        ok, res = _decide(pc)
        assert ok, (name, pc.check_id, res.status.value, [d.code for d in res.diagnostics], pc.description)
    # nothing this stage reports about correct work is an error
    assert all(f.severity != "error" for f in plan.findings)
    assert all(f.code not in ("ST-INTERNAL-001",) for f in plan.findings)


def test_booklet_and_unknown_unit_readings_fail_only_as_warnings():
    for text, profile in (("E = hf = 3.3 × 10⁻¹⁹ J with f = 5.0 × 10¹⁴ Hz.", "physics"),
                          ("Efficiency = 150 kJ m⁻² yr⁻¹ / 1500 kJ m⁻² yr⁻¹ × 100 = 10%", "ess")):
        plan = build_checks(build_document(text, None, profile), report_id="r", request_id="q")
        assert plan.checks and all(pc.failure_severity == "warning" for pc in plan.checks if pc.relation_kind in ("sub", "eq"))


def test_a_space_grouped_thousand_is_withheld_never_failed():
    # the front end reads '126 000' as 126 (a plain space is no thousands separator in its grammar): the check is withheld
    for text in ("Using Q = mcΔT = 0.50 × 4200 × (80 − 20) = 126 000 J ≈ 1.3 × 10⁵ J.",
                 "ΔH = −q/n = −(50.0 × 4.18 × 5.0)/0.0250 = −41 800 J mol⁻¹ = −41.8 kJ mol⁻¹",
                 "KE = ½mv² = 0.5 × 1200 × 25² = 375 000 J = 375 kJ = 3.75 × 10⁵ J"):
        plan = build_checks(build_document(text, None, "physics"), report_id="r", request_id="q")
        for pc in plan.checks:
            assert _decide(pc)[0], (text, pc.check_id)
        assert any(f.code == "ST-PARSE-001" and "digits" in f.message for f in plan.findings)


def test_a_wrong_substituted_value_in_a_step_is_still_caught():
    # STEM repair 7 (rule solved-law): 'f = 3.0/(2π)' right after 'ω = 2πf' evaluates the law solved for f (f = ω/(2π)), so it is no longer
    # read as an algebra step from the law (that reading failed correct working); the wrong value substituted for ω (3.0, where '2π/ω =
    # 2π/4.0' substituted 4.0) is still caught, by that substitution, set against the value substituted before as the step had pinned it:
    # exactly that check fails, and the same line with the right value holds
    plan = build_checks(build_document("T = 2π/ω = 2π/4.0 = 1.57 s and ω = 2πf so f = 3.0/(2π) = 0.48 Hz", None, "physics"), report_id="r", request_id="q")
    failed = [pc for pc in plan.checks if not _decide(pc)[0]]
    assert [pc.check_id for pc in failed] == ["stem-sub-1"], [(pc.check_id, pc.description[:120]) for pc in failed]
    assert "'f = 3.0/(2π)'" in failed[0].description and "rule solved-law" in failed[0].description
    right = build_checks(build_document("T = 2π/ω = 2π/4.0 = 1.57 s and ω = 2πf so f = 4.0/(2π) = 0.64 Hz", None, "physics"), report_id="r", request_id="q")
    assert right.check("stem-sub-1") is not None and all(_decide(pc)[0] for pc in right.checks)
