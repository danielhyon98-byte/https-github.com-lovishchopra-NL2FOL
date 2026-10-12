# STEM results (stage `corpus-eval`)

Measured results for STEM support (docs/STEM_DESIGN.md, sections 13, 16 and 17). Everything below was run in
this development container (4 CPUs shared with other work, Python 3.13.16, Z3 reporting version 5.1.0) on 2026-10-12. The figures guard
against regressions. They are not capacity claims, and nothing here was run against a live provider or a deployment.

**Scope.** A check that holds shows that the statement *as encoded* (the reading of the answer the front end
built, the IR, the tolerance policy) is consistent or entailed. It does not show that the physics, chemistry or
mathematics of the answer is right, that the reading matches the author's intent, or that statements the front end
did not read are correct. A relation outside the encodings is named undecided (INT-SUBJ-002 with its reason) and is
never shown as success.

Reproduce:

```
python -m pytest -q tests/stem/test_corpus.py                 # the corpus evaluation (564 tests)
python tests/stem/test_corpus.py                              # the summary printed below (PYTHONPATH=src:tests/stem)
python tests/stem/data/build_stem_corpus.py                   # rebuilds stem_corpus.json (a test pins equality)
python -m pytest -q -m stress tests/stress/test_stem_stress.py   # section 13 targets; JSON in tests/stress/results/stem.json
```

## 1. The corpus

`tests/stem/data/stem_corpus.json` (schema `stem_corpus/1.0`) has **558 items**:

| Role | Items | Built here | Copied fixtures (`tests/fixtures/stem/corpus`, verbatim) | Probe answers (`tests/channel/test_stem_channel.py`) |
| --- | --- | --- | --- | --- |
| correct | 236 | 181 | 46 | 9 |
| mutant (one fault, or two in one probe) | 292 (293 faults) | 241 | 38 | 13 |
| rounding-only control | 30 | 30 | 0 | 0 |

| Subject | Correct | Mutant | Control |
| --- | --- | --- | --- |
| Physics | 72 | 70 | 10 |
| Chemistry | 42 | 59 | 11 |
| Biology | 14 | 26 | 3 |
| Environmental Systems and Societies | 12 | 17 | 0 |
| Sports, Exercise and Health Science | 9 | 30 | 3 |
| Design Technology | 9 | 26 | 2 |
| Mathematics: Analysis and Approaches (and one AA HL probe) | 46 | 34 | 0 |
| Mathematics: Applications and Interpretation | 14 | 11 | 1 |
| Computer Science | 18 | 19 | 0 |

The items use **45 notation tags**. The largest groups are Unicode maths (287), Unicode unit exponents (137), inline
LaTeX (123), LaTeX units (114), ASCII (100), slash units (69), display LaTeX (45), chemical equations (33), implicit
multiplication (27) and derivation lines (21). Smaller groups cover scientific notation in Unicode, LaTeX, ASCII, `e`
and `*` forms, signed values, fractions and surds, Greek symbols, per cent, °C/K, logarithms, part labels,
comparisons, supplied data, concentration brackets, calculus, ionic charges, inequalities, code blocks, ratios, bond
notation, hydrate dots, ± and coordinates.

**How the labels are made.** The labels never come from the implementation. `corpus_lib.py` computes them with
exact `Fraction` and integer interval arithmetic over the values the builder writes. A correct step holds at the
written values: |C − S| ≤ h(S) with τ = 0, and h = 0 for exact work. A fault must fail over the *widest* reading:
every decimal operand ranges over [w − h(w), w + h(w)], constants are hulled with their booklet values, integers
with trailing zeros are widened, and the band is h_wide(S) + |C|/20. Substitution and restatement faults need
|a − b| > h_wide(a) + h_wide(b). The builder drops any mutant it cannot prove; the auto-generated ones are the
leading-digit slip, power of ten, sign and restatement. Every fault stores its proof in the item. A control rounds
one stated result to one fewer significant figure, and the item stores the proof that this still holds.
The builder caps eight common classes at 22 mutants each, chosen round-robin over subjects. It keeps every other
mutant, every correct answer and every control.

**One label note.** Fixture `stem-math-021` labels only its stated fault. In its mutant, the step
`x = 8 is the solution` follows from the faulty line, so the copy lists it under `affected_steps`. An error on that
step is the fault propagating, not a false finding. The fixture file itself is unchanged.

## 2. Corpus evaluation (`tests/stem/test_corpus.py`)

Every item goes through `RouterHub` (open task → dispatch → receive), and the receipt is checked against the gold.
**All 564 tests pass** (22.4 s), so every item meets every criterion below:

- **Recall.** Each injected fault is named by one of its expected codes, on a claim that covers the fault text.
  Where the class has a check kind, the failing formal check is of that kind (`stem-<kind>-N`, linked by its signed
  `formal_result_id`).
- **Precision.** No correct or control item has an error-level finding. None carries INT-SUBJ-004, ST-DIM-001/002,
  ST-UNDEF-001 or ST-ALG-001 unless its gold expects it, and none has a failed formal check. In a mutant, every error
  or INT-SUBJ-004 names a claim covering a fault or a step the fault affects.
- **Verbatim delivery.** The delivered report text equals the sent text, and every claim is a substring of it.
- **Nothing raised**, and each item was received within the design bound of 2.5 s: p50 38 ms, p95 77 ms, max 139 ms.
- **Undecided relations named with a reason.** Each of the 8 items whose gold lists out-of-scope relations has
  INT-SUBJ-002 with that reason. These are a derivative, a definite integral, a factorial, a limit, a complex
  number, asymptotic notation, a fractional power and a stated derivative.
- **The 13 silent passes seen before STEM support** are all caught or named: P1, P3, P5, P7, P8, P10, C1, C2, M2,
  M3, M4, B1 and CS1.

Recall per fault class (named / injected):

| Class | Named | Check kind | Expected code |
| --- | --- | --- | --- |
| arithmetic_slip | 36/36 | eq | INT-SUBJ-001 |
| sign_error | 25/25 | eq, res | INT-SUBJ-001 |
| power_of_ten | 24/24 | eq, cnv, sub | INT-SUBJ-001 |
| wrong_operator | 23/23 | eq, sub | INT-SUBJ-001 |
| wrong_substitution | 23/23 | sub | INT-SUBJ-001 |
| wrong_restatement | 23/23 | res | INT-SUBJ-001 |
| misstated_given | 23/23 | giv | INT-SUBJ-004 |
| dimension_error | 23/23 | — | ST-DIM-001 / ST-DIM-002 |
| dropped_factor | 12/12 | sub, eq | INT-SUBJ-001 |
| unit_conversion | 12/12 | cnv, eq | INT-SUBJ-001 |
| wrong_rearrangement | 11/11 | alg | INT-SUBJ-001 |
| wrong_comparison | 8/8 | cmp | INT-SUBJ-001 |
| lost_root | 6/6 | sol | INT-SUBJ-001 / ST-ALG-001 |
| show_that_mismatch | 6/6 | tgt | INT-SUBJ-004 |
| unbalanced_atoms | 6/6 | chem | INT-SUBJ-001 |
| unbalanced_charge | 4/4 | chem | INT-SUBJ-001 |
| wrong_base_conversion | 6/6 | base | INT-SUBJ-001 |
| wrong_boolean_identity | 5/5 | bool | INT-SUBJ-001 |
| wrong_truth_table_row | 4/4 | tt | INT-SUBJ-001 |
| fixture and probe classes (prose_percent_change 3, wrong_derivative 2, unbalanced_equation, unstated_value, unreadable_equation, wrong_identity, undefined_expression, fractional_power_misuse, offset_scale_relative_change, booklet_value_unstated 1 each) | 14/14 | as labelled | as labelled |
| **total** | **293/293** | | |

**Undecided rate.** These are the relations read on the 236 correct items that were checked or named undecided.

| Subject | All correct items: undecided / relations | Typical items (gold lists no out-of-scope relation) |
| --- | --- | --- |
| Physics | 0 / 320 (0 %) | 0 / 320 |
| Chemistry | 1 / 125 (0.8 %) | 1 / 125 |
| Biology | 0 / 43 | 0 / 43 |
| ESS | 0 / 22 | 0 / 22 |
| SEHS | 0 / 36 | 0 / 36 |
| Design Technology | 0 / 35 | 0 / 35 |
| Mathematics AA | 16 / 141 (11.3 %) | 7 / 122 (5.7 %) |
| Mathematics AI | 0 / 19 | 0 / 19 |
| Computer Science | 1 / 26 (3.8 %) | 0 / 23 |
| **All subjects** | **18 / 767 (2.3 %)** | **8 / 745 (1.1 %)** |

The test asserts that the overall rate is below 10 % and that each subject's typical rate is below 10 %. Over all
items, Mathematics AA exceeds 10 % because the corpus deliberately includes 7 out-of-scope items (design section 15).
The 7 typical undecided relations in Mathematics AA all come from copied fixtures `stem-math-008/010/011/013`:
symbolic powers, derivatives, an integral and an antiderivative evaluated between limits. The one Chemistry relation
is a Σ in `stem-chem-010`. Each is named with its reason.

## 3. Arena: STEM mutations (`scripts/arena/stem_mutations.py`, `run_arena.py`)

`run_arena.py` now adds three mutations, and only for subjects routed to a STEM branch (sciences, mathematics,
computer science):

- `stem_arithmetic_slip`: the leading digit of one stated result in a worked chain moves by 3. Expected INT-SUBJ-001.
- `stem_wrong_unit`: the unit of the first stated result whose left side has quantities with units and an operator
  is swapped for a unit of another dimension (`15 m s⁻¹` becomes `15 m s⁻²`). Expected ST-DIM-001 or ST-DIM-002.
- `stem_substitution`: a value given in the request, where the answer uses it as an operand in a calculation (not a
  `Given` line or a stated value), has its leading digit moved by 3 at that one place. Expected INT-SUBJ-001.

The site locators are linear scans with no regular expressions. They are bounded on 200,000-character adversarial
input, as `tests/stem/test_arena_stem_mutations.py` checks. A mutation with no site in an answer is skipped. The
six shared mutations (`MUTATIONS`) and the History/English rounds are unchanged.

In a contained round (four STEM answers and one History answer, `test_a_contained_round_…`), there were 40 records
and 0 failures. Every STEM injection was functional and named by its expected code: arithmetic slip 4/4,
substitution 4/4, wrong unit 2/2 (the other two answers have no unit-bearing site). The History answer got the genuine answer
and the shared mutations that have a site in it, and no STEM variant. No genuine answer carried an error.

## 4. Section 13 targets (`tests/stress/test_stem_stress.py`, `-m stress`)

| Target | Measured | Asserted |
| --- | --- | --- |
| p95 hub receive, typical 3-part Physics answer, below 250 ms | 60 answers with varied values, 13 checks each, 0 errors: p50 129 ms, p95 188 ms, max 213 ms | p95 < 250 ms, 0 errors |
| a 128-check answer below 2.5 s | 140 steps: 128 checks, all satisfied, ST-LIM-002 for the rest; 1.22 s | < 2.5 s |
| adversarial 400,000-character input through the front end below 1.5 s | the design mix of 100,000 characters each of nested `(`, unclosed `$x = 1 `, `1e1e…`, 30-digit numbers: best of 5 runs 1.09 s (runs 1.09 to 1.55 s on a shared machine), ST-LIM-001/002 and ST-SCOPE-001, no ST-INTERNAL-001 | best < 1.5 s |
| unchanged suite time for the non-STEM tests | the 1803 tests outside `tests/stem`: base revision 31.8 s and 27.7 s, this stage 28.1 s and 29.4 s (two runs each) | non-STEM receipts build no STEM document and carry no STEM check or ST- finding (History, Economics, English, Business) |
| the labelled corpus through the hub | 558 items: p50 37 ms, p95 77 ms, max 169 ms, total 21.3 s | every item < 2.5 s |

**Single patterns at 400,000 characters.** These were recorded but not asserted, because the design target is the
mixed input. The figures are the best of 2 runs:

| Pattern | Time |
| --- | --- |
| nested brackets | 0.57 s |
| 30-digit numbers | 0.29 s |
| `1e1e…` | 1.64 s |
| unclosed `$x = 1 ` | 1.81 s |

The last two are above 1.5 s. Each one is a pure-Python linear pass over about 400,000 tokens (lexing, run finding,
name pre-scan, segmentation). That is no regression; the base revision measured 2.6 s and 2.1 s for them.

**Front-end speed changes.** These were made to meet the mixed-input target. The mix took 1.50 s at the base
revision (best of 2) and 1.63 s with this stage's reading fixes before the speed changes (best of 3), against
1.09 s after (best of 5):

- The lexer reads brackets first.
- One-character punctuation tokens come from a module-level table.
- Two-character operators are sliced only after their opening character.
- Identifiers are not built twice.
- The subscript and prime readers run only at their opening characters.
- The scientific forms are tried only at `e`/`E`, a space or a times sign.
- A span-finder scan returns its extent without calling `_finish`.
- The run finder skips a bracket that never closes, where `extend` would stop at once.
- The reading view is computed once per document.
- Non-space counts use `str.split`.
- The pre-scan's subscript map is built once.

Evidence that they change nothing:

- Lexer tokens equal the base revision's on 1,125 texts (the corpus answers and questions, plus edge cases) in both
  modes, with and without values: 4,500 token lists.
- Document output (statements, relations, findings, prose values) equals the output before the speed changes for
  2,815 (text, profile) cases.
- Pre-scan names equal the base revision's.
- `test_lexer_extents_agree_with_and_without_values` and `test_lexer_fast_paths_…` pin this.

## 5. STEM module fixes found by the corpus

Every fix is pinned in `tests/stem/test_reading_extensions.py` (99 tests, including 15 adversarial inputs on the new
paths, each bounded below 3 s and never raising out of the hub). No gold label was changed to make an item pass.

| Module | Fix |
| --- | --- |
| `document.py` | A restatement written as one inline-LaTeX value is a prose value. A minus before a prose number is its sign, but a hyphen is not. A signed per cent starts at its sign. A chemical equation inside one `\mathrm{…}`/`\text{…}`/`\ce{…}` wrapper is read. A show-that target is never taken from bracketed data. |
| `segment.py` | A derivation line followed on the same line by a sentence of prose splits before the sentence. |
| `spans.py` | Parenthesised unit denominators are handled (`J/(g K)`). A word-formula label may end in a superscript or a per cent (`BMI = mass/height² = …`). A colon glued to a figure and followed by a space ends a step label (`Step 1: …`). |
| `units.py` | `unit_group` reads a bracketed unit group. |
| `parser.py` | Adds the names `SV`, `HR`, `BMI` and `RQ`, and unit groups after `/`. Euler's number to a closed power is read as `exp` (maths profiles). Σ over integer bounds (at most 24 terms) is read as its terms. A derivative `f′(x)` stays unsupported but keeps its name and argument. |
| `lexer.py` | A hexadecimal numeral that opens with a digit is read (`2A₁₆`, Computer Science). |
| `nodes.py` | `Unsupported` gains `name` and `arg`. `replace_symbol` rebuilds each node type explicitly (no reflection) under a depth bound. |
| `relations.py` | Integer coefficients are dimensionless on symbolic sides (`½mv²`). Order chains are read (`T₁ = 300 K > T₂ = 250 K`). Result cues include participles before *at*/*as*, and step words include *we get*, *obtain*, *yields* and *leads to*. A restatement in an unknown unit pairs only with the same unit. Boolean name definitions are read, and a truth-table column they head is checked. A factorisation inside a chain is checked as an identity. A function or derivative evaluated at a point is checked against the stated formula. Complex values are named undecided. |
| `checks.py` | A reordered substitution matches each factor once (bounded injective matching). A ratio equality `a:b = c:d` is compared by cross products. |

## 6. Known gaps (measured, not fixed in this stage)

- Function names other than `f`, `g` and `h` (for example `C(12)`) are read as products. Corpus item `mai-func-1`
  is therefore labelled with its correct form only.
- The unit `yr` is not in the unit table (existing tests pin this). An answer that uses it gets the structural
  finding ST-UNIT-001, and its relation is checked as written only. A failing check there is INT-SUBJ-004 (design
  section 6.4), so the gold of the built ESS answers marked `unknown_units` (`ess-npp-*`, `ess-eff-1`)
  also accepts INT-SUBJ-004 for their arithmetic faults (9 mutants). The corpus marks such items `unknown_units`.
- A vector magnitude `|\vec{v}|` gives ST-PARSE-001.
- Exponential equations such as `e^{2x} = 4` stay undecided.
- Single-pattern adversarial inputs at 400,000 characters (`1e1e…`, unclosed `$`) take 1.6 to 1.8 s; see section 4.
- The engine compile step dominates the cost of each check (about 8 of 16 ms). That is outside the STEM modules.

## 7. Suite

The full suite passes: 3470 passed, 45 deselected (stress), 4 xfailed (pre-existing engine defects outside this
stage) in 72 s. The baseline before this stage was 2788 passed, 40 deselected and 4 xfailed in about 45 s. The new
tests are 564 corpus tests (22.4 s, almost all of it engine verification), 99 reading-extension tests and 19 arena
tests. With `-m stress`, the five STEM stress tests pass in 47.5 s.
