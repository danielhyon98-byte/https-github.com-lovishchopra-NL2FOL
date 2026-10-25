# STEM encodings (stage `checks` of docs/STEM_DESIGN.md)

This stage turns every planned relation of a `StemDocument` into an IR 1.0 problem that the
Z3 engine decides, or into an ST finding that names the relation as undecided and says why.
Nothing here evaluates agent text. The AST nodes of `nodes.py` are translated one by one into
allowlisted IR nodes, as plain data (`dict`). Python's exact `Fraction` arithmetic only:
- builds literals, unit factors, half-widths and decimal exponents;
- computes enclosure bounds;
- refuses undefined encodings.

Every verdict on a stated relation is an engine result.

```python
from epinoic_logic.stem import build_document
from epinoic_logic.stem.checks import build_checks

doc = build_document(answer, request, "physics")
plan = build_checks(doc, report_id="r1", request_id="q1")   # relay: relay=True (no giv/tgt)
plan.checks     # PlannedCheck(check_id, kind, description, claim_ids, problem, expected_if_sound,
                #              policy, failure_severity, inconsistent_is_failure=False, form, readings)
plan.findings   # CheckFinding(code="ST-...", severity, message, statement_ids, check_id)
```

`PlannedCheck.problem` is the JSON form that `Problem.model_validate` accepts. The branch stage
validates it and turns it into a `FormalCheck`, and the engine validates it again inside
`verify`. `stem/` imports nothing outside itself. That is why the problem is data here and not
a `Problem` object. It also keeps the front-end import allowlist of
`tests/stem/test_front_end_safety.py` unchanged.

## Modules

| Module | Role |
| --- | --- |
| `constants.py` | The data-booklet constants table: values, accepted values, units, profiles, ambiguous letters. D3a (`match_written`) and D3b (`booklet_reading`). |
| `enclosures.py` | The exact-value table (`exact_trig`, `exact_log`). Rational enclosures (`enclose`) for π, e and the trigonometric, inverse trigonometric, ln, log₁₀, log_b and exp functions, by outward-rounded interval arithmetic. `cross_check` against `math`. |
| `scaling.py` | Decimal-exponent factoring. A `Term` is `⟦expr⟧ × 10^k`. Short literals stay as written, and long ones are split. Frames for comparisons; `LiteralTooLong` → ST-LIM-001. |
| `tolerance.py` | `STEM_TOLERANCE_RULE` (R1 to R10), `SHORT_RULE` (≤ 300 characters), `STEM_SCOPE`, `half_width`, `tau_for`, `band_expr`. |
| `to_ir.py` | `Encoder` (AST → IR terms with auxiliaries, guards and enclosures), `ProblemBuilder`, one-to-one `ir_name`, `grounding`, `inspect_ir` (bounds and the nonlinear rule, read from the IR as data). |
| `checks.py` | `build_checks`: a `PlannedCheck` per planned kind, or an ST finding. |

## Node encodings (section 7.4)

| Construct | Encoding | Policy |
| --- | --- | --- |
| quantity | the literal × its exact SI factor (SI reading), or the literal as written | linear |
| `+ − unary−` | `add` (flattened, nested beyond 32 arguments), `sub`, `neg` | linear |
| `× · *`, juxtaposition | `mul` | nonlinear when two factors hold variables |
| `a / b`, b a literal | `div`; an exact zero is ST-UNDEF-001 | linear |
| `a / b`, otherwise | `q`: `Q_DEF q·b = a`, `GUARD b ≠ 0`. A closed b that is exactly 0 is ST-UNDEF-001. A closed b whose admissible values include 0 is ST-UNDEC-001. | linear when b is closed |
| `xⁿ` (2 ≤ n ≤ 12) | `mul` of n copies of a literal, a small closed term or a variable; a larger compound base gets `P_DEF p = x` | linear when x is closed |
| `x⁰`, `x⁻ⁿ` | `1` with `GUARD x ≠ 0` (0⁰ is ST-UNDEF-001); `q·xⁿ = 1` with a guard | as `xⁿ` |
| `√x` | `sq`: `S_SQ sq ≥ 0 ∧ sq·sq = x` (an odd decimal exponent is moved into x first). A closed negative x is ST-UNDEF-001. | nonlinear |
| `\|x\|` | `ite(x ≥ 0, x, −x)` | linear |
| `n %` | `n/100` (SI reading), `n` (as written) | linear |
| `a mod b`, `a div b` (also `//`, `\bmod`, `%` in Computer Science, a stated remainder, a congruence) | `to_real(mod(a, b))`, `to_real(idiv(a, b))` with the IR's integer operators; `a` a non-negative whole-number expression as written (`+ − ×`, powers up to 12, nested integer operations), `b` a positive whole number as written; anything else ST-UNDEC-001 with the reason | linear |
| `±`, `∓` | the sign of the reading. `eq` and `sub` require both choices (AND); a step's relations take either (OR); roots expand to two. | as the operands |
| exact-table function | sin/cos/tan of multiples of 30° and 45° (and the same angles as rational multiples of π): `q` or `q·sq` with `sq·sq = 2` or `3`. Also log₁₀ and log_b of exact powers, ln 1, exp 0, and the inverse functions at table values in degrees. | as the surd |
| other function, π, e | `enc` with `ENC_LO ≤ enc ≤ ENC_HI` (forces Form S) | linear |
| `b^x` with b and x closed and no unit, x no integer (`RealPower`: `10^(−8.2)`, `2^{1/3}`) | its exact value when rational and it fits one literal (`16^{3/4} = 8`, `enclosures.exact_real_power`); otherwise `enc` of `exp(x·ln b)` for b > 0, cross-checked against `math.pow` (forces Form S; an algebra step holding one is ST-UNDEC-001, since a step is compared exactly); `0^x = 0` for x > 0; a zero base under a non-positive exponent is ST-UNDEF-001, a base that is or may be negative ST-UNDEC-001 | linear |
| `bⁿ` with b closed and no unit, n an integer beyond 12 and up to 1000 (`RealPower`: `(1 + 0.065/12)^{-60}`, `1.003^{144}`, `2^{20}`) | its exact value when it fits one literal (`2^{20} = 1048576`; a negative base takes the sign of n's parity); otherwise `enc` of the outward-rounded interval power `Interval.power(n)` of b, cross-checked against `math.pow` (forces Form S; an algebra step holding one is ST-UNDEC-001); a zero base under a power that is not positive is ST-UNDEF-001; a value beyond about 10^±300 is ST-UNDEC-001 and is never computed | linear |
| a power of e or of a positive closed base with no unit, its exponent in symbols (`e^(kt)`, `2^(t/3)`, `(1/2)^(t/5)`) | no value: ST-UNDEC-001 ('a symbolic power'), the base and the exponent kept on the node; an `alg` step whose unknown appears only in powers of e reads `u = e^(−k)` (`SIDE_POS`); in a `mod` check, `B^X` with `X = c + Σ qᵢ·mᵢ` is `B^c · Π uᵢ^(qᵢ/sᵢ)` over positive variables `uᵢ = B^(sᵢ·mᵢ)` (`U_POS`; bounded by the enclosure of `B^(sᵢ·range)` when every symbol of mᵢ has a stated value, `U_LO`/`U_HI`), sᵢ the step of mᵢ's coefficients, a power beyond the degree bound ST-LIM-001 | nonlinear when two factors hold variables |
| function of an unknown, `f(x)`, `Unsupported(reason)` | ST-UNDEC-001 with the reason | — |
| Boolean `∧ ∨ ¬ ⊕` | `and`, `or`, `not`, `not(iff)` | linear |
| based numeral | its exact value (Int in `stem-base`) | linear |

Auxiliary definitions are memoised by the canonical shape of their subtree within one problem
and one reading. The same quotient, root or function value therefore shares one symbol across
the premise and the conclusion of a step.

Angles:
- An argument written with `°` is in degrees.
- An argument holding π is in radians.
- Otherwise it is ambiguous, and two readings are built: degrees and radians.
- The result of an inverse function is likewise read in both units.

## Symbols and groundings

- **Names.** Symbols map one-to-one into `^[a-z][a-z0-9_]{0,63}$` (`ir_name`): `v` → `s_v`,
  `V` → `s_cap_v`, `v₀` → `s_v_0`, `Δv` → `s_delta_v`, `θ` → `s_theta`, `f′` → `s_f_prime`. A
  numeric suffix is added on collision. Per-reading copies carry `_r2`, `_r3`.
- **Auxiliaries.** `q_n`, `p_n`, `sq_n`, `enc_n`, `x_n` (interval operands), `w_n` (substituted
  values), `root_n`, `k_n` and `t_<el>_<l|r>` (balances), `o_<row>_<col>` (truth tables), `u_n`
  (the positive variables of a model check), and `c`, `r`, `l` (the compared values). User
  symbols always start with `s_`, so they never collide with these.

| Premise | Grounding kind |
| --- | --- |
| `C_DEF`, `R`, `W`, `L_DEF`/`R_DEF` of compared values; the report's figures; bindings stated in the report | `supplied_text`, `verified` (located in the report) |
| a value located in the request | `task_setting`, `verified` |
| `PREV` (the preceding relation of a step), `FORMULA` (a stated law) | `specialist_inference` |
| `GUARD_*`, `SIDE_ROOT` (principal root), a booklet value for an unstated symbol | `assumption` (the engine lists them in `ungrounded_dependencies`) |
| `REL` (the relation of a model check, as written) | `supplied_text`, `verified` |
| `Q_DEF`, `S_SQ`, `P_DEF`, tallies, step definitions, `ENC_*`, `U_POS`, `U_LO`/`U_HI`, a written constant widened to its booklet value | `arithmetic_fact` (encoding devices; the note says so; no check verifies them, so since engine 0.4.0 the engine lists them in `unverified_dependencies`, which no STEM decision reads) |

Every problem's `notes` starts with the STEM scope statement (`tolerance.STEM_SCOPE`). Notes
also record:
- "policy: nonlinear" when that policy is used;
- "decimal exponent factored: 10^F" when a frame other than 0 is used;
- the readings.

`notes` is part of the problem digest, so the result binding covers them.

## Forms (D6, R4)

**Form E** (no operand has an interval reading). The query is an entailment.
- Premises `C_DEF: c = ⟦E⟧` and `R: r = S`, plus the auxiliaries and the guards.
- Conclusion `STATED: |c − r| ≤ h + τ·|c|`.
- Expected: ENTAILED. A COUNTEREXAMPLE shows `c` beside `r`. In the observed case
  `(20 − 0)/4.0 = 6.0 m s⁻²` it shows `c = 5`, `r = 6`. The core contains `C_DEF` and `R`, so
  the result is never vacuous (E108).

**Form S** (some operand has an interval reading). The query is a satisfiability query.
- Interval readings: a carried intermediate, a written constant, a booklet value, an
  enclosure, or a measured binding of an evaluated symbol.
- Premises: the interval premises, the definitions, and `BAND`.
- Expected: SATISFIABLE.
- UNSATISFIABLE means that no admissible reading of the rounded values gives the stated value.
  SATISFIABLE never means "true", and the description says so.
- Every symbol of a Form S problem is pinned, interval-bounded or an auxiliary defined by a
  premise. A free symbol is refused (ST-INTERNAL-001), so it can never make the query vacuously
  satisfiable. The one exception is a `mod` check, whose query is whether the relation has a
  solution at all: its variables (the model's variable and the symbols with no stated value)
  have the role `variable`, and the description and the notes say that SATISFIABLE never shows
  that the relation holds for every value.
- A guard that could fail inside an interval would make the query unsatisfiable for a reason
  that is no fault of the stated value. Such a divisor is therefore refused first (ST-UNDEC-001).

**Readings** (section 6.4) are a disjunction, at most 4 per check (ST-PARSE-002 beyond):
- as written, and SI;
- each reading of an ambiguous unit (`M`, `ms⁻¹`);
- angles in degrees or radians;
- an operand's two implicit-multiplication readings.

The rules for picking them:
- Every numeral carries a unit: SI only.
- An antilogarithm set against a concentration (`[H⁺] = 10^(−8.2) = 6.31 × 10⁻⁹ mol dm⁻³`, a
  lone power of ten with no unit on one side, a value in a concentration unit on the other):
  SI only, the power read in mol dm⁻³ (the unit the pH, pOH, pKa and pKb scales are defined
  in). Read as a bare number in SI it would take a unit prefix, an integer power of ten, for a
  change of its exponent (`10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³` in mol m⁻³). The label says so.
- A bare numeral appears with units: both.
- No unit anywhere: as written.
- When every unit factor is 1 and nothing is a per cent, SI and as written coincide, and one
  reading is kept.
- An unrecognised unit: as written only, with `failure_severity="warning"`.

Numbers in a reading:
- The affine offset of °C/°F is applied only in an explicit conversion, and not when the
  statement speaks of a change.
- A Given value, a constant the answer states, and an exact coefficient are taken as written.

## The checks (section 8.1)

| Kind | What the problem decides | Form and expectation |
| --- | --- | --- |
| `eq` | `E = S`. τ = 1/100 (1/20 for ≈ or "about"). Exact mode: τ = 0, h = 0. A value set against a value adds its own half-width. A stated value with its absolute uncertainty (`1600 ± 32`, stated for a computed side with no `±`) widens h by the uncertainty. | E or S |
| `sub` | **Pairs**: each substituted value matches a binding of its symbol, as written or in SI (R7). A value written in another order of the same product or sum also matches. **Evaluation**: the symbolic side under its bindings (or substitution readings, or a booklet reading admitted by a dimension check) against the numeric side. | E (pairs); E or S |
| `alg` | `PREV` (with guards and the principal-root side condition) entails the next relation. Bindings, substitution readings (a line that writes the preceding relation with values put in) and up to 8 stated formulas are included for the symbols that appear on one side only. A rounded decimal in the step is compared within its band. Warning when the step brings in symbols that nothing connects. A step whose unknown appears only in powers of e (`e^(−8k)`) is decided in `u = e^(−k)` with the side condition `u > 0` (`SIDE_POS`). An antiderivative (`∫6t dt = 3t²`) is an `alg` check from `D = D` to `D = integrand`, D being the derivative of the stated antiderivative formed by the STEM pack (power rule), so it holds iff the polynomials agree for every value. | E |
| `mod` | A model evaluation: an equality that applies an exponential model of the answer or the request at an argument (`P(t + 4) = P₀e^(k(t + 1))` after `P = P₀e^(kt)`; the model's letter glued to its bracket, `models.py`). The model's expression stands at the written argument; some value of the variables, and of the stated symbols within their stated values, must satisfy the relation, every power of an exponent in symbols read through positive variables (above). The relaxation only widens the solutions: UNSATISFIABLE proves that no value satisfies the relation; SATISFIABLE never shows that it holds. A letter defined as two models gives one pair of sides per definition (at most 4 combinations), as a disjunction: the relation must hold under one of them. Planned only when the relaxation fits (planning-time `relaxation_fits`); a written decimal, a unit, the model's own definition, a space before the bracket and the sciences reading of e keep the old reading. | S, SATISFIABLE |
| `sol` | Exact roots: linear membership (the root substituted as written) and, when the full set is claimed with no domain restriction and exact parameters, completeness (`EQ ⊢ ∨ x = rᵢ`). Decimal roots: a root of the equation in each rounding interval (R10), or completeness over the intervals when the full set is claimed. A root the answer states in prose for the quantity it named by the symbol (`relations._described_roots`): membership only, in Form S, over its rounding interval widened by τ = 1/100 of its value. | E; S for membership of decimal roots |
| `cnv` | `|C − S| ≤ h(S) + h(C)` in SI, τ = 0 (R5). Unknown unit atoms that are the same on both sides cancel. | E |
| `cmp` | Values: `l op r` exactly (R6). Bound symbols with several values: some admissible values satisfy it. Steps: as `alg`. | E (or S) |
| `res` | `|S − S′| ≤ h(S) + h(S′)` (R8); a rounding the prose states for S′ gives h(S′) (rule `rounding-cue`); the start of a named change (rule `named-change`) at warning severity. | E |
| `giv` | The Given value matches a request value of the same symbol or dimension (R7), a quantity the request names in words included. Warning. A value the prose takes from a supplied table against the table's cells taken as written, `|S − D| ≤ h(S)` (R9, rule `table-data`). Warning. | E |
| `tgt` | The final value matches the show-that target (τ = 1/20 when the target says "about"). Warning. | E |
| `chem` | Coefficients pinned (Int, or Real for fractional ones); tallies `t_<el>_l`, `t_<el>_r` and `t_charge_*`. Conclusion: every tally balances. | E |
| `bool` | `NEG: ¬(lhs ⇔ rhs)`. A witness distinguishes the sides. | satisfiability, UNSATISFIABLE |
| `tt` | Stated outputs pinned per row; every output `⇔` its expression on the row's inputs. | E |
| `base` | Exact Int arithmetic on based numerals. | E |

Every check has these fields:
- `inconsistent_is_failure=False` (D13).
- `failure_severity`: `error` unless a reading the report did not state was used, in which case
  `warning`. Such readings: a booklet value, an unknown unit, symbol identity across texts, a
  show-that target, or a step with unconnected symbols.
- `policy`: `nonlinear` exactly when the IR has a `mul` with two factors that hold variables
  (the validator's rule). `inspect_ir` reads it from the data, and the tests compare it with
  `engine.policies.required_policy`.
- A description of at most 1,200 characters, in the form
  `<what>: '<statement>' [claims …] [<short rule>] <form; policy; readings; details>`.

## Withheld relations (operands the front end may have cut)

The checks stage decides only relations whose two sides are whole, so a misreading by the
front end can never become an error. A relation is withheld (ST-PARSE-001, warning, the check
id named) when any of these holds:
- An arithmetic operator adjoins one of its operands in the text (`xy + y = …` read as
  `+ y = …`).
- An operand opens with a sign right after a symbol-like token or a stray character, rather
  than after a line start, a relation sign, a bracket, a separator or a prose word.
- Prose stands between the two sides of one link (`3 and ａ = 5` read as `3 = 5`). The relation
  sign, LaTeX commands, alignment marks and the words of verbal arithmetic (`equals`, `is equal
  to`, `gives`) are allowed there.

Operands read from the request (targets, request equations) and single prose values (`res`,
`giv`) are not looked at. These guards only ever withhold a check; none decides one.

## Undecided (ST findings of this stage)

| Code | When |
| --- | --- |
| ST-UNDEF-001 | Division by an exact zero, an even root of a negative value, the logarithm of a non-positive value, 0⁰, tan at a pole, arcsin/arccos outside [−1, 1]. No problem is built. |
| ST-UNDEC-001 | A function of an unknown, an enclosure argument beyond its bound, a divisor whose admissible values include zero, a construct outside the encodings (with the reason), an integer remainder or quotient (`mod`, `div`) of a negative number or a number that is not whole as written, or by a divisor that is not a positive whole number (languages round a negative remainder differently). |
| ST-UNDEC-002 | A symbol with no stated value and no admissible booklet reading. |
| ST-LIM-001 | A literal still over 40 digits after factoring; IR bounds (48 symbols, 128 premises, 2,000 nodes, depth 40, polynomial degree 24); more than 6 interval operands. |
| ST-PARSE-002 | More than 4 readings. |
| ST-INTERNAL-001 | An enclosure that fails its cross-check against `math`, or an internal failure while building one check. The other checks are still built. |

Each finding names the planned check id. The front end's own findings (ST-PARSE-001,
ST-DIM-*, ST-UNIT-*, ...) stay on `StemDocument.findings`.

## Bounds

- Enclosures:
  - trigonometric arguments up to 10⁹ radians (reduced modulo 2π);
  - ln and log over [10⁻¹⁰⁰, 10¹⁰⁰];
  - exp over |x| ≤ 700;
  - at most 400 series terms;
  - 192-bit outward rounding;
  - width ≤ 10⁻¹⁵·max(1, |mid|);
  - bounds written with 25 significant digits.
- Interval operands: at most 6 per check.
- Readings: at most 4 per check.
- IR: the engine's default `Limits` and 48 symbols per check.
