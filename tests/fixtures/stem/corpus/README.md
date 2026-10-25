# Labelled STEM corpus

84 specialist answers, one JSON file per item, for the `corpus-eval` stage of `docs/STEM_DESIGN.md`.
Each answer mixes equations and prose the way IB Physics, Chemistry, Mathematics, Biology and ESS
tutors write: given values, an equation, a substitution, a result with its unit, and a sentence of
explanation. 38 items carry exactly one injected fault. The other 46 are fully correct, and many of
them are deliberately tricky.

| Subject | Items | With a fault | Correct |
| --- | --- | --- | --- |
| Physics | 35 | 17 | 18 |
| Chemistry | 20 | 9 | 11 |
| Mathematics: Analysis and Approaches | 17 | 7 | 10 |
| Mathematics: Applications and Interpretation | 4 | 3 | 1 |
| Biology | 5 | 1 | 4 |
| Environmental Systems and Societies | 3 | 1 | 2 |

Topics covered:
- **Physics.** Kinematics, forces, energy and power, momentum, circular motion, gravitation,
  circuits, waves, thermal physics and gas laws, nuclear physics, photons.
- **Chemistry.** Moles and masses, concentration, gas laws, enthalpy, equilibrium and pH, balanced
  and ionic equations.
- **Mathematics.** Rearrangement, quadratics, logarithms, derivative and integral steps, sequences
  and series, surds and indices, coordinate geometry.
- **Biology and ESS.** Magnification, osmosis, the Lincoln index, Hardy–Weinberg, cardiac output,
  energy transfer, productivity, doubling time.

## Schema

```json
{
  "id": "stem-phys-001",
  "subject": "Physics",
  "task_type": "short_answer | structured_answer | show_that",
  "question": "the router's request text",
  "supplied_texts": [ { "document_id": "...", "title": "...", "text": "...", "locator_scheme": "none", "provenance": "..." } ],
  "response_text": "the specialist's answer, verbatim",
  "notation": ["unicode", "latex_inline", "..."],
  "gold": {
    "faults": [ { "kind": "arithmetic_slip", "step": "...", "expected_codes": ["INT-SUBJ-001"], "note": "..." } ],
    "correct_steps": ["...", "..."]
  }
}
```

- `supplied_texts` entries validate as `translate.contracts.SuppliedText`. Three items carry a data
  table: `stem-chem-009`, `stem-chem-010` and `stem-ess-001`.
- `question` is plain text. It is what `RouterHub.dispatch` sends, and it is the request text that
  STEM bindings, `stem-giv` and `stem-tgt` read.

## Label semantics

- **`step`** is an exact substring of `response_text`, and it occurs exactly once. It holds the
  faulty link, with both endpoints where the fault is a relation. A test maps a step to the claim
  (or claims) whose offsets cover it.
- **`faults`** is empty for a correct item. Otherwise it holds exactly one fault.
- **`expected_codes`** lists the codes, from the design's finding table, that correctly name the fault
  on the receipt. They must attach to a claim that covers the step.
  - A fault counts as named when **any** listed code appears.
  - The first code is the one the design prefers.
  - Two codes are listed only where the design itself allows both:
    - `stem-phys-031`: a failed substitution (INT-SUBJ-001) and a sum of different dimensions
      (ST-DIM-002).
    - `stem-math-021`: a lost negative root. ST-ALG-001 names the step, and the stem-sol
      completeness check refutes the claim "x = 8 is the solution".
    - `stem-math-020` listed two (a fractional power: ST-PARSE-001 in the code table, ST-UNDEC-001
      in the grammar's Unsupported list) until the end-to-end run1 detection fixes. A closed base
      raised to a closed fractional exponent is now one value the engine decides, so the fault is
      relabelled with the stronger INT-SUBJ-001 alone (the engine refutes `16^(3/4) = 16 × 3/4`).
    - `stem-ess-002`: an arithmetic slip in kJ m⁻² yr⁻¹. If `yr` is not in the unit table,
      ST-UNIT-001 lowers the failure to INT-SUBJ-004. The design's table (section 6.1) does not
      list `yr` today, so as written the design reports INT-SUBJ-004 here. INT-SUBJ-001 stays
      first because the slip rests only on stated figures.
- **`kind`** is the mutation class. Classes:
  - arithmetic slip; wrong operator; power-of-ten error; dropped factor; sign error;
  - wrong substitution; wrong rearrangement; lost root; wrong identity;
  - unit-conversion error; wrong prose restatement; wrong prose percentage change; wrong comparison;
  - unbalanced equation (atoms); unbalanced charge;
  - misstated given; show-that mismatch; booklet value for an unstated symbol;
  - dimension error; relative change on an offset scale;
  - unstated value; unreadable equation; wrong derivative; fractional power misuse; undefined
    expression.
- **`note`** gives the true value and the reason. It ends with the exact computation that
  justifies the label, in brackets, for example `[computed: C=5 S=6.0 h=0.05 tau=1/100 -> does not
  hold]`.
- **`correct_steps`** are worked steps that are true. A test must find no error-severity finding and
  no INT-SUBJ-004 on a claim that holds only correct steps.
  - The list includes substitutions, arithmetic, conversions, restatements, balanced equations,
    algebra rows, and correct steps that lie outside the encodings (derivatives, integrals,
    fractional and symbolic powers). The last group may be named undecided (a warning), but never
    an error.
  - In a faulty item, a step that faithfully carries the faulty value forward is in neither list.
    For example, `10 / 3.0 = 3.3` after a wrong momentum total is true arithmetic and is listed,
    but "The trolleys move off together at 3.3 m s⁻¹" restates a wrong result and is not.
  - A correct item must also receive no INT-SUBJ-001, INT-SUBJ-003 or INT-SUBJ-004 anywhere. Its
    `original_response` must be delivered verbatim.

## How the labels were computed

- **The tolerance rule.** Every label was computed with exact `fractions.Fraction` arithmetic under
  the STEM tolerance rule of the design (section 5.2):
  - R1: the half-width of the last written digit;
  - R2: τ = 1/100 for `=`, 1/20 for `≈`, and 0 with h = 0 in exact mode;
  - R4: a sign-aware band;
  - R5: conversions with τ = 0;
  - R6: exact comparisons;
  - R7: substitution;
  - R8: restatements;
  - R9: prose relations (quant's 5 % band with a 0.5-point floor).
- **Enclosures.** π, logarithms and exponentials use rational enclosures from series with explicit
  remainder bounds. Square roots use exact integer-root bounds. Surds are checked exactly as
  a + b√d.
- **Rounded intermediates.** Where a correct step depends on a carried value, the step was checked
  both at the written value and over its rounding interval.
- **Faults.** Every faulty step fails under every admissible reading. Every correct step holds.
- **No text is evaluated.** The script that built the corpus never evaluated any item text. Each
  check was written by hand as Fraction arithmetic, and the text was searched only for the step
  substrings.

## Notation tags

`notation` lists every notation the answer uses:
- **Math markup.** `latex_inline`, `latex_display` (including `align*`), `unicode`, `ascii`,
  `code_block`.
- **Scientific notation.** `sci_unicode` (`× 10⁸`), `sci_ascii` (`x 10^8`), `sci_latex`
  (`\times 10^{8}`), `sci_e` (`6.67e-11`, `6.0E-3`), `sci_star` (`10**-19`).
- **Units.** `units_unicode_exponent` (`m s⁻²`), `units_ascii_exponent` (`kg^-2`), `units_slash`
  (`m/s²`), `units_dot` (`kg·m/s²`), `units_latex` (`\text{m s}^{-1}`), `units_prefix`,
  `temperature_celsius_kelvin`.
- **Other.**
  - Prose and layout: `percent`, `prose_relation`, `part_labels`, `derivation_lines`.
  - Symbols: `implicit_multiplication`, `subscripted_symbols`, `greek_symbols`,
    `fractions_surds`, `signed_values`.
  - Chemistry: `chemical_equation`, `ionic_charges`, `hydrate_dot`, `bond_notation`,
    `atom_tally`, `concentration_brackets`.
  - Mathematics: `logarithm`, `calculus`, `trig_degrees`, `plus_minus`, `absolute_value`,
    `inequality`, `comparison`, `ratio`, `coordinates`.
  - Miscellaneous: `currency_dollar`, `magnification_suffix`, `supplied_data`.

mmHg is out of scope and does not occur.

## Deliberately tricky correct items

Each of these is correct work that a careless reading would flag:
- **Rounding and constants.**
  - `stem-phys-002`, `stem-phys-008`: g written as 9.8 where 9.81 is given or customary.
  - `stem-phys-004`, `stem-phys-013`, `stem-chem-017`: rounded intermediates carried forward.
  - `stem-phys-005`: trailing zeros of integers.
  - `stem-phys-028`: `u` after a number is the atomic mass unit.
- **Integer measured data.** `stem-phys-030` divides integer measured data and rounds the result to
  2 s.f., saying so: `200 km ÷ 3 h = 67 km h⁻¹`. Under an exact-mode reading of R2 (every operand an
  integer, so τ = 0 and h = 0) this would be a false error. The implementation must not apply exact
  mode to measured quantities.
- **Ambiguous units.**
  - `stem-phys-032` writes `ms⁻¹` for metres per second. Read literally it is "per millisecond";
    an ambiguous unit must become a disjunction or a warning, never an error.
  - `stem-ess-001` uses `yr⁻¹`, which is not in the design's unit table.
- **Symbols that look like units.**
  - `stem-phys-011`: g after a number is gram, and ms is a millisecond.
  - `stem-phys-013`: T is a period.
  - `stem-phys-034`: R is the normal reaction.
  - `stem-phys-035`: N is a count.
  - `stem-bio-003`: N is a population.
  - `stem-math-004`: c is a coefficient.
  - `stem-math-019`: PV and FV are two-letter symbols.
- **Implicit multiplication and notation that looks like something else.**
  - `stem-math-001`, `stem-math-009`, `stem-phys-018`: `y(x + 1)`, `x(x − 3)` and `I(R + r)` are
    products, not function applications.
  - `stem-chem-005`: `n(NaOH)` and `c(...)` are chemistry notation.
  - `stem-chem-014`: an atom tally, `C 3 = 3; H 8 = 4 × 2 = 8`.
  - `stem-chem-019`: bond notation `O=O` and `H–H` inside an arithmetic chain.
- **Scope and layout.**
  - `stem-phys-033`: v and E_k are rebound in part (b), so ST-SCOPE-001 at most.
  - `stem-phys-018`: the working sits in a code block, so ST-CODE-001 at most.
  - `stem-chem-010`, `stem-bio-002`: continuation lines that begin with `=`.
- **Signs and percentages.**
  - `stem-chem-008`: a ΔT in °C used as kelvin.
  - `stem-bio-002`: −6.0 % restated as "lost 6.0 %".
  - `stem-bio-004`: 0.48 restated as 48%.
  - `stem-math-003`: dividing an inequality by −2.
- **Outside the encodings.**
  - `stem-math-008`, `stem-math-010`, `stem-math-011`, `stem-math-013`: symbolic and decimal
    powers, derivatives and integrals. These are named undecided, never errors. Since STEM repair 11
    the derivative of a polynomial is decided by the power rule (`stem-math-011`'s derivative holds,
    `stem-math-012`'s wrong one fails, INT-SUBJ-001).
  - `stem-chem-010`: Σ in a stated definition.
- **Exact answers.**
  - `stem-math-004`, `stem-math-017`: surds.
  - `stem-math-016`, `stem-phys-027`: fractions.
  - `stem-math-019`: `$` used as currency, with no closing `$` that could open LaTeX.

## Baseline before STEM support

This baseline was measured by sending every item through `RouterHub` on this branch before the
`branch` stage. All 84 items route to `generic`. One of the 38 faults is named for the right
reason: the prose percentage in `stem-phys-009`, through quant. `stem-phys-026` receives
CORE-QNT-001, but for the wrong reason ("no figures are stated with it"), because today's quant
does not read °C figures. No correct item receives an error today. The corpus measures what the
STEM stages must add without adding false errors.
