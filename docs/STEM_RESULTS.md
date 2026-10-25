# STEM results

Measured results of STEM support (Physics, Chemistry, Biology, ESS, SEHS, Design Technology,
Mathematics AA and AI, Computer Science) on branch `stem-build`; section 10.1 records its merge
into the round-7 development branch. The design is docs/STEM_DESIGN.md. Everything below was run in this development
container (4 CPUs shared with other work, Python 3.13.16, Z3 reporting version 5.1.0) on
2026-10-12. The figures guard against regressions. They are not capacity claims. Nothing here
was run against a live provider or a deployment, and no answer below was written by a live
specialist agent.

**Scope.** A check that holds shows that the statement *as encoded* (the reading of the answer
the front end built, the IR, the tolerance policy) is consistent or entailed. It does not show
that the physics, chemistry or mathematics of the answer is right, that the reading matches the
author's intent, or that statements the front end did not read are correct. A relation outside
the encodings is named undecided (an ST finding, or INT-SUBJ-002, with its reason) and is never
shown as success. Every STEM problem carries this statement in its `notes`:

> STEM check: proves a property of its encoding only. It proves that the written arithmetic,
> substitution, conversion, algebraic step, balance or Boolean identity holds, or does not hold,
> under the stated premises, the documented readings and the STEM tolerance rule. It does not
> establish that a law applies, that data are true, that a model is physically valid, that a unit
> is the right one beyond the dimension and conversion checks, or that the answer is what the
> question wanted.

## At a glance

| Measure | Result |
| --- | --- |
| Full suite | 3470 passed, 45 deselected (stress), 4 xfailed, no failures and no errors, in 74.20 s (section 8) |
| Implementation-stage evaluation: the 84 labelled answers written before implementation | 38 of 38 injected faults named with an expected code; 0 errors on the 46 correct answers; no misses and no misplaced errors; slowest receipt 130.6 ms (section 2) |
| Corpus evaluation: 558 items (236 correct, 292 mutants carrying 293 faults, 30 rounding-only controls) | 293 of 293 faults named; no error on any correct or control item; all 564 corpus tests pass (section 3) |
| The case observed before STEM support: `a = (20 - 0)/4.0 = 6.0 m s⁻²` (true value 5.0) | before: routed to `generic`, ACCEPTED, no finding, no check. Now: routed to `sciences`; `stem-eq-1` is a COUNTEREXAMPLE with `c = 5`, `r = 6`; INT-SUBJ-001 (error) on claim `s1.2`; delivered ACCEPTED_WITH_FINDINGS |
| The 13 silent passes seen before STEM support | all 13 caught or named |
| Relations on correct answers named undecided | 18 of 767 (2.3 %); 8 of 745 (1.1 %) on the items whose gold lists no out-of-scope relation |
| Evaluation of agent text | none: no path evaluates agent text (section 6) |
| Review rounds and the STEM arena with live specialists | **not run in this build** (section 1); results will go to section 10 |

## 1. What was run in this build, and what was not

**Run here.** The five stages of the design (`core`, `engine`, `checks`, `branch`,
`corpus-eval`), each with its own tests; the labelled corpora (sections 2 and 3); a contained
arena round on recorded answers with the STEM mutations (section 4); the stress targets
(section 5); the no-eval audit (section 6); and the full suite (section 8). Every answer used
here was written for the tests: the 84 fixture answers, the built corpus items, the probe
answers of the channel tests and the recorded arena answers.

**Not run here.** The review rounds (the overseer audits of each stage) and the STEM arena with
live specialist agents. The founder had the STEM build run as one integrated system with the
main arena instead. The main arena merges this branch (in round 7 when the merge is ready,
otherwise in round 8) and tests STEM there with a STEM lens and a STEM fixer. Section 10 is kept
for those rounds.

**How STEM will be tested there, honestly stated.** In the integrated arena the STEM answers
come from real STEM specialist agents on the cheapest model tier. Each specialist is configured
only from its own v4 knowledge base (its full-context bundle), with no MyLib or textbook
library. That is a different and harder test than this build ran:

- The specialists will write in whatever mix of notation they choose. This build measured only
  answers written for the tests, so it cannot say how often live answers fall outside the
  grammar (ST-PARSE-001), outside the encodings (ST-UNDEC-001) or into a reading the front end
  gets wrong.
- Without a textbook library, a specialist may state a constant, a formula or a datum from its
  bundle alone. The checks decide only whether the written working holds under the stated
  premises; they never establish that a law, constant or datum is correct (the scope above).
- Nothing in this document is evidence about live agents. The rates here (recall, false
  errors, undecided relations, timings) hold for the labelled corpora only.

## 2. Implementation-stage evaluation: 84 labelled answers

`tests/fixtures/stem/corpus/` holds 84 specialist-style answers, one JSON file each, written and
labelled before any STEM code existed (its README gives the schema and the label rules). Each
answer mixes equations and prose the way IB tutors write: given values, an equation, a
substitution, a result with its unit, and a sentence of explanation. These answers were the
acceptance bar of the build. The final evaluation sent every one through `RouterHub` (open task,
dispatch, receive) on the final revision and compared the receipt with the gold.

### Composition

| Subject | Items | With one fault | Correct |
| --- | --- | --- | --- |
| Physics | 35 | 17 | 18 |
| Chemistry | 20 | 9 | 11 |
| Mathematics: Analysis and Approaches | 17 | 7 | 10 |
| Mathematics: Applications and Interpretation | 4 | 3 | 1 |
| Biology | 5 | 1 | 4 |
| Environmental Systems and Societies | 3 | 1 | 2 |
| **Total** | **84** | **38** | **46** |

- Task types: 68 short answers, 14 structured answers, 2 show-that answers.
- 44 notation tags. The most frequent: Unicode maths (68 items), Unicode unit exponents (32),
  implicit multiplication (27), derivation lines (21), unit prefixes (20), subscripted symbols
  (16), chemical equations (15), inline LaTeX (13), ASCII (13), scientific notation in Unicode
  (12).
- Many correct answers are deliberately tricky: `g` written as 9.8 where 9.81 is customary,
  rounded intermediates carried forward, integer measured data rounded to 2 s.f.
  (`200 km ÷ 3 h = 67 km h⁻¹`), `ms⁻¹` for metres per second, `g` and `ms` as units, `T`, `R`,
  `N` and `c` as symbols, `y(x + 1)` as a product, bond notation and atom tallies inside an
  arithmetic chain, a ΔT in °C used as kelvin, an inequality divided by −2, surds and fractions,
  `$` as currency, and calculus that must be named undecided, never flagged.

**How the labels were made.** Never from the implementation. Every label was computed by hand
with exact `fractions.Fraction` arithmetic under the STEM tolerance rule, with rational
enclosures for π, logarithms and exponentials. Every fault fails under every admissible reading,
and every correct step holds. Each fault's note ends with the exact computation that justifies
it, for example `[computed: C=5 S=6.0 h=0.05 tau=1/100 -> does not hold]`. No item text was
evaluated to build them.

### Faults (38 faults in 25 classes)

| Class | Faults | Expected code (any listed code names it) |
| --- | --- | --- |
| arithmetic slip | 6 | INT-SUBJ-001 (one item also accepts INT-SUBJ-004: its unit `yr` is not in the unit table) |
| unit-conversion error | 4 | INT-SUBJ-001 |
| sign error | 3 | INT-SUBJ-001 |
| wrong rearrangement | 2 | INT-SUBJ-001 |
| lost root | 2 | INT-SUBJ-001, or ST-ALG-001 |
| dropped factor | 2 | INT-SUBJ-001 (one item also accepts ST-DIM-002) |
| unbalanced equation (atoms); unbalanced charge | 1; 1 | INT-SUBJ-001 |
| wrong operator; power-of-ten error; wrong substitution; wrong identity; wrong comparison; wrong prose restatement; wrong prose percentage change | 1 each | INT-SUBJ-001 |
| misstated given; show-that mismatch; booklet value for an unstated symbol | 1 each | INT-SUBJ-004 (warning: each rests on a reading the report did not state) |
| dimension error | 1 | ST-DIM-001 |
| relative change on an offset scale | 1 | CORE-QNT-001 |
| unstated value | 1 | ST-UNDEC-002 |
| unreadable equation | 1 | ST-CHEM-001 |
| wrong derivative | 1 | ST-UNDEC-001 (calculus is outside the encodings) |
| undefined expression | 1 | ST-UNDEF-001 |
| fractional power misuse | 1 | ST-PARSE-001 or ST-UNDEC-001 when measured; INT-SUBJ-001 since the e2e run1 detection fixes, which decide a closed fractional power (docs/STEM_DESIGN.md, section 33) |

### Before and after

| | Before STEM support (the fixture README's baseline) | After (final revision) |
| --- | --- | --- |
| Routing | all 84 answers to `generic` | every answer to its STEM branch |
| Faults named for the right reason | 1 of 38 (the prose percentage in `stem-phys-009`, through quant); `stem-phys-026` received CORE-QNT-001 for the wrong reason | **38 of 38**, each by an expected code on a claim that covers the fault's step |
| Errors on correct work | none | **none** on the 46 correct answers |
| Misplaced errors in faulty answers | — | none: every error names a claim covering the fault or a step it affects |
| Slowest receipt | — | 130.6 ms (the design bound is 2.5 s) |

Each correct answer was also delivered verbatim (the report text equals the sent text, and every
claim is an offset substring of it). Re-running the evaluation while writing this document gave
the same counts; timings vary with the load on the shared machine.

Reproduce (the 84 fixture items keep their `stem-` ids inside the corpus test):

```
python -m pytest -q tests/stem/test_corpus.py -k "stem-"     # 84 passed
```

## 3. Corpus evaluation: the 558-item corpus

`tests/stem/data/stem_corpus.json` (schema `stem_corpus/1.0`) extends the fixtures with items
built here and the probe answers of the channel tests. A re-run of its summary at the final
revision gave counts identical to those below.

```
python -m pytest -q tests/stem/test_corpus.py                 # the corpus evaluation (564 tests)
python tests/stem/test_corpus.py                              # the summary printed below (PYTHONPATH=src:tests/stem)
python tests/stem/data/build_stem_corpus.py                   # rebuilds stem_corpus.json (a test pins equality)
```

### Composition

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

The items use **45 notation tags**. The largest groups are Unicode maths (287), Unicode unit
exponents (137), inline LaTeX (123), LaTeX units (114), ASCII (100), slash units (69), display
LaTeX (45), chemical equations (33), implicit multiplication (27) and derivation lines (21).
Smaller groups cover scientific notation in Unicode, LaTeX, ASCII, `e` and `*` forms, signed
values, fractions and surds, Greek symbols, per cent, °C/K, logarithms, part labels,
comparisons, supplied data, concentration brackets, calculus, ionic charges, inequalities, code
blocks, ratios, bond notation, hydrate dots, ± and coordinates.

**How the labels are made.** The labels never come from the implementation. `corpus_lib.py`
computes them with exact `Fraction` and integer interval arithmetic over the values the builder
writes. A correct step holds at the written values: |C − S| ≤ h(S) with τ = 0, and h = 0 for
exact work. A fault must fail over the *widest* reading: every decimal operand ranges over
[w − h(w), w + h(w)], constants are hulled with their booklet values, integers with trailing
zeros are widened, and the band is h_wide(S) + |C|/20. Substitution and restatement faults need
|a − b| > h_wide(a) + h_wide(b). The builder drops any mutant it cannot prove; the
auto-generated ones are the leading-digit slip, power of ten, sign and restatement. Every fault
stores its proof in the item. A control rounds one stated result to one fewer significant
figure, and the item stores the proof that this still holds. The builder caps eight common
classes at 22 mutants each, chosen round-robin over subjects. It keeps every other mutant, every
correct answer and every control.

**One label note.** Fixture `stem-math-021` labels only its stated fault. In its mutant, the
step `x = 8 is the solution` follows from the faulty line, so the copy lists it under
`affected_steps`. An error on that step is the fault propagating, not a false finding. The
fixture file itself is unchanged.

### Results

Every item goes through `RouterHub` (open task → dispatch → receive), and the receipt is checked
against the gold. **All 564 tests pass**, so every item meets every criterion below:

- **Recall.** Each injected fault is named by one of its expected codes, on a claim that covers
  the fault text. Where the class has a check kind, the failing formal check is of that kind
  (`stem-<kind>-N`, linked by its signed `formal_result_id`).
- **Precision.** No correct or control item has an error-level finding. None carries
  INT-SUBJ-004, ST-DIM-001/002, ST-UNDEF-001 or ST-ALG-001 unless its gold expects it, and none
  has a failed formal check. In a mutant, every error or INT-SUBJ-004 names a claim covering a
  fault or a step the fault affects.
- **Verbatim delivery.** The delivered report text equals the sent text, and every claim is a
  substring of it.
- **Nothing raised**, and each item was received within the design bound of 2.5 s (p50 38 ms,
  p95 77 ms, max 139 ms in the recorded run).
- **Undecided relations named with a reason.** Every relation the gold lists as out of scope
  (in 8 correct items, and in 3 mutants built from them) is named on a covering claim with
  ST-UNDEC-001 and its reason. These are a derivative, a definite integral, a factorial, a
  limit, a complex number, asymptotic notation, a fractional power and a stated derivative.
  (Since the e2e run1 detection fixes the fractional power `16^{3/4}` is read, and the relation that
  holds it is named for its fourth root: docs/STEM_DESIGN.md, section 33.)
  (STEM repair 10, section 10.6: a definite integral of a polynomial with whole-number limits is
  now checked, so math-calc-2's gold lists its integral as two checks, not as undecided.)
- **The 13 silent passes seen before STEM support** are all caught or named: P1, P3, P5, P7,
  P8, P10, C1, C2, M2, M3, M4, B1 and CS1.

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

**Undecided rate.** These are the relations read on the 236 correct items that were checked or
named undecided.

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

The test asserts that the overall rate is below 10 % and that each subject's typical rate is
below 10 %. Over all items, Mathematics AA exceeds 10 % because the corpus deliberately includes
7 out-of-scope items (design section 15). The 7 typical undecided relations in Mathematics AA
all come from copied fixtures `stem-math-008/010/011/013`: symbolic powers, derivatives, an
integral and an antiderivative evaluated between limits. The one Chemistry relation is a Σ in
`stem-chem-010`. Each is named with its reason.

## 4. Arena mutations on recorded answers (`scripts/arena/stem_mutations.py`, `run_arena.py`)

`run_arena.py` adds three mutations, and only for subjects routed to a STEM branch (sciences,
mathematics, computer science):

- `stem_arithmetic_slip`: the leading digit of one stated result in a worked chain moves by 3.
  Expected INT-SUBJ-001.
- `stem_wrong_unit`: the unit of the first stated result whose left side has quantities with
  units and an operator is swapped for a unit of another dimension (`15 m s⁻¹` becomes
  `15 m s⁻²`). Expected ST-DIM-001 or ST-DIM-002.
- `stem_substitution`: a value given in the request, where the answer uses it as an operand in a
  calculation (not a `Given` line or a stated value), has its leading digit moved by 3 at that
  one place. Expected INT-SUBJ-001.

The site locators are linear scans with no regular expressions. They are bounded on
200,000-character adversarial input, as `tests/stem/test_arena_stem_mutations.py` checks. A
mutation with no site in an answer is skipped. The six shared mutations (`MUTATIONS`) and the
History and English rounds are unchanged.

In a contained round on recorded answers (four STEM answers and one History answer,
`test_a_contained_round_…`), there were 40 records and 0 failures. Every STEM injection was
functional and named by its expected code: arithmetic slip 4/4, substitution 4/4, wrong unit 2/2
(the other two answers have no unit-bearing site). The History answer got the genuine answer
and the shared mutations that have a site in it, and no STEM variant. No genuine answer carried
an error. This round used no live agent; the live STEM arena is the integrated arena's
(section 10).

## 5. Stress targets (`tests/stress/test_stem_stress.py`, `-m stress`)

Design section 13. Figures recorded in `tests/stress/results/stem.json`.

| Target | Measured | Asserted |
| --- | --- | --- |
| p95 hub receive, typical 3-part Physics answer, below 250 ms | 60 answers with varied values, 13 checks each, 0 errors: p50 129 ms, p95 188 ms, max 213 ms | p95 < 250 ms, 0 errors |
| a 128-check answer below 2.5 s | 140 steps: 128 checks, all satisfied, ST-LIM-002 for the rest; 1.22 s | < 2.5 s |
| adversarial 400,000-character input through the front end below 1.5 s | the design mix of 100,000 characters each of nested `(`, unclosed `$x = 1 `, `1e1e…`, 30-digit numbers: best of 5 runs 1.09 s (runs 1.09 to 1.55 s on a shared machine), ST-LIM-001/002 and ST-SCOPE-001, no ST-INTERNAL-001 | best < 1.5 s |
| unchanged suite time for the non-STEM tests | the 1803 tests outside `tests/stem`: base revision 31.8 s and 27.7 s, this stage 28.1 s and 29.4 s (two runs each) | non-STEM receipts build no STEM document and carry no STEM check or ST- finding (History, Economics, English, Business) |
| the labelled corpus through the hub | 558 items: p50 37 ms, p95 77 ms, max 169 ms, total 21.3 s | every item < 2.5 s |

**Single patterns at 400,000 characters.** These were recorded but not asserted, because the
design target is the mixed input. The figures are the best of 2 runs:

| Pattern | Time |
| --- | --- |
| nested brackets | 0.57 s |
| 30-digit numbers | 0.29 s |
| `1e1e…` | 1.64 s |
| unclosed `$x = 1 ` | 1.81 s |

The last two are above 1.5 s. Each one is a pure-Python linear pass over about 400,000 tokens
(lexing, run finding, name pre-scan, segmentation). That is no regression; the base revision
measured 2.6 s and 2.1 s for them.

**Front-end speed changes** made to meet the mixed-input target. The mix took 1.50 s at the base
revision (best of 2) and 1.63 s with the corpus stage's reading fixes before the speed changes
(best of 3), against 1.09 s after (best of 5): the lexer reads brackets first; one-character
punctuation tokens come from a module-level table; two-character operators are sliced only after
their opening character; identifiers are not built twice; the subscript and prime readers run
only at their opening characters; the scientific forms are tried only at `e`/`E`, a space or a
times sign; a span-finder scan returns its extent without calling `_finish`; the run finder
skips a bracket that never closes; the reading view is computed once per document; non-space
counts use `str.split`; and the pre-scan's subscript map is built once. Evidence that they
change nothing: lexer tokens equal the base revision's on 1,125 texts in both modes, with and
without values (4,500 token lists); document output equals the output before the speed changes
for 2,815 (text, profile) cases; pre-scan names equal the base revision's; and
`test_lexer_extents_agree_with_and_without_values` and `test_lexer_fast_paths_…` pin this.

## 6. Safety: no evaluation of agent text

**Final audit.** All of `src/epinoic_logic` (`stem/`, `branches/` including `stem_pack.py`,
`adapters/` including `stem_specialist/`, `translate/`, `channel/`, `integrity/`, `engine/`,
`ir/`) was searched for `eval(`, `exec(`, bare `compile(`, `sympify`, `parse_expr`,
`__import__`, `pickle`, `marshal`, `literal_eval`, `globals()`/`locals()`,
`subprocess`/`os.system`, sympy and numexpr imports, `ast` use and dynamic `getattr`. None of
these is used on agent text:

- every `compile(` is `re.compile` of a constant pattern;
- the one `eval(` is `engine/procedures.py`: Z3's `model.eval` on an already compiled Z3 symbol,
  not a string;
- there are no sympy, numexpr, pickle, `ast` or `__import__` imports;
- `importlib.import_module` appears only in `cli.py` and `service/app.py`, on fixed module names
  and on `epinoic_logic.adapters.<adapter_id>`, where the adapter id comes from the operator's
  command line or service configuration, never from specialist output, and stays inside the
  `epinoic_logic.adapters` namespace;
- every `getattr` in the STEM modules uses a literal attribute name; the `getattr` calls with a
  variable name iterate fixed tuples or schema fields (the validator's child fields,
  `Limits.model_fields` in the runner, fixed field tuples in `integrity/envelope.py`, the IR node
  fields in `cross_check.py`).

Result: no path evaluates agent text. The IR is data, and only allowlisted nodes are compiled.

**Enforced by tests** (design section 14): `tests/stem/test_front_end_safety.py` (an AST scan
of every `stem/` module, an import allowlist, a meta-test that the scan catches each forbidden
form, and adversarial inputs), `tests/stem/test_checks_safety.py` (the checks-stage modules:
`math` only in the enclosure cross-check, no `Fraction` from a string constant) and
`tests/stem/test_parser_claims.py` (the STEM adapter, the STEM pack, the hub hooks, the SI
reading and `quant.py`).

## 7. STEM module fixes found by the corpus

Every fix is pinned in `tests/stem/test_reading_extensions.py` (99 tests, including 15
adversarial inputs on the new paths, each bounded below 3 s and never raising out of the hub).
No gold label was changed to make an item pass.

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

## 8. Suite

```
python -m pytest -q          # 3470 passed, 45 deselected, 4 xfailed in 74.20 s
python -m pytest -q -m stress tests/stress/test_stem_stress.py   # the five STEM stress tests
```

- **Final run:** 3470 passed, 45 deselected (the stress tests), 4 xfailed, no failures and no
  errors, in 74.20 s.
- **The 4 xfails** are strict markers in `tests/engine/test_pack_policies.py`, added in stage
  `engine` to document defects that predate the STEM work and lie outside it (no IR schema or
  validator change was in scope): the identifier, assertion-id and numeric-literal patterns end
  in `$`, so a trailing newline is accepted as part of an identifier or literal (`x\n` is a
  symbol distinct from `x`; 3 parametrised cases); and a lone surrogate in a text payload gives
  INTERNAL_ERROR (E900) instead of INVALID_FORMALIZATION (E100). The surrogate case stays a
  non-success status, which a separate passing test pins. Each marker is strict, so it fails
  the suite once the defect is fixed and the marker has to be removed.
- **Before stage `corpus-eval`** the suite was 2788 passed, 40 deselected and 4 xfailed in about
  45 s. That stage added 564 corpus tests (about 22 s, almost all of it engine verification), 99
  reading-extension tests and 19 arena-mutation tests. With `-m stress`, the five STEM stress
  tests pass in 47.5 s.

## 9. What remains open

**Not yet done.**
- The review rounds (overseer audits of each stage) and the STEM arena with live specialists:
  folded into the integrated arena (section 1). Until then nothing here is evidence about live
  answers.
- The overseer audit and the user's sign-off on the recorded behaviour changes of design
  section 18 (STEM subjects no longer route to `generic`, which changed two existing
  assertions; E108 now reads as undecided; SATISFIABLE where UNSATISFIABLE is expected now reads
  as failed; aliases match on word boundaries; INT-SUBJ findings carry claim ids; the new codes
  INT-SUBJ-004 and BR-INTERNAL-001).
- The merge of `stem-build` into the infrastructure. The main checkout is changing in parallel,
  so the suite has to be re-run on the merged tree.

**Known gaps, measured, not fixed in this build.**
- Function names other than `f`, `g` and `h` (for example `C(12)`) are read as products. Corpus
  item `mai-func-1` is therefore labelled with its correct form only. (Since the second e2e repair
  an application of an exponential model the answer or the request defines is read as the model at
  its argument in a `stem-mod` check, and no algebra step is read over an application of a letter
  the text defines as a function: docs/STEM_DESIGN.md, section 33, item 5. Any other use of such an
  application keeps the product reading.)
- A unitless calculation stated in a prefixed unit is read as written and in SI (design section
  6.4), so a stated value off by exactly the unit's factor holds in SI (`c = 0.25 × 4 = 0.001 mol
  dm⁻³`: 1 mol m⁻³). Only an antilogarithm stated as a concentration is read in one unit (section
  21, item 1); no injection of the arena harness produces this fault.
- The unit `yr` is not in the unit table (existing tests pin this). An answer that uses it gets
  the structural finding ST-UNIT-001, and its relation is checked as written only. A failing
  check there is INT-SUBJ-004 (design section 6.4), so the gold of the built ESS answers marked
  `unknown_units` (`ess-npp-*`, `ess-eff-1`) also accepts INT-SUBJ-004 for their arithmetic
  faults (9 mutants).
- A vector magnitude `|\vec{v}|` gives ST-PARSE-001.
- Exponential equations such as `e^{2x} = 4` stay undecided.
- Single-pattern adversarial inputs at 400,000 characters (`1e1e…`, unclosed `$`) take 1.6 to
  1.8 s (section 5).
- The engine compile step dominates the cost of each check (about 8 of 16 ms). That is outside
  the STEM modules. `src/epinoic_logic/engine/README.md` records two recommended changes to
  `procedures.py` (outside the STEM stages) and the slow case of the smaller root of a quadratic
  inside a narrow interval (100 to 180 ms).
- The two pre-existing IR schema and validator defects behind the 4 xfails (section 8): a
  trailing newline accepted in identifiers and literals, and E900 instead of E100 for a lone
  surrogate. Both are outside the STEM stages. STEM problems are built as data by the pack:
  identifiers are `s_…` transliterations (`to_ir.ir_name` turns `x` and a newline into `s_x_ua`) and literals
  are written from exact values, and the channel refuses text with a lone surrogate before it
  is parsed (INT-REQ-009).
- **A false warning observed while writing this document** (not part of any corpus): the
  correct answer `Given: u = 0 m s⁻¹, v = 20 m s⁻¹, t = 4.0 s. a = (v − u)/t = 5.0 m s⁻².` to
  the request "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its
  acceleration." gets INT-SUBJ-004 (warning) from `stem-giv-1`. The request states u = 0 only in
  words ("from rest"), so the Given value is compared with the request's only velocity, 20 m s⁻¹.
  It is a warning, never an error, and the same answer with `u = 0` (no unit) gets no finding.
  It is recorded here for the STEM lens of the integrated arena.

**Out of scope by design** (design section 15): the truth of laws, data and constants;
symbolic calculus (except an indefinite integral of a polynomial with its stated antiderivative,
design section 20.5, and a definite integral of a polynomial with whole-number limits, section 30),
vectors, matrices, complex numbers, factorials and asymptotic notation (named
undecided); unit correctness beyond dimension warnings and explicit conversions;
significant-figure policy; program behaviour (code is never run); diagrams and graphs; method
quality.

## 10. Integrated arena results

### 10.1 The merge into the round-7 development branch, measured on the recorded rounds

`stem-build` was merged into the development branch (the round-5 to round-7 arena fixes) as one
translator (design section 20). The merge was measured on 2026-10-12 by replaying every recorded
arena round on copies with the merged tree's harness (the recorded rounds are never written). These
are replays of recorded answers: no specialist was called, and nothing ran against a live provider
or a deployment.

| Round | Development branch | Merged |
| --- | --- | --- |
| r1 | 30/30 functional | 30/30 |
| r1-adv | 150/151 (the planted empty answer is REJECTED, as it must be) | 150/151 (the same) |
| r2, r3, r4, r5, r6 | 46/46 each | 46/46 each |
| r7 | 162/162 | 177/177: the 162 recorded transmissions and the 15 STEM mutations of the round-7 STEM answers, each named with its expected code on the injected claim (14 INT-SUBJ-001, 1 ST-DIM-001) |

- In every round the records that carry error-level findings are the same set, with the same codes,
  as on the development branch: no genuine receipt gains an error.
- The 9 round-7 STEM answers yield the same 201 claims as on the development branch, in the same
  order, with the same texts, roles, proposed kinds, materiality, supports and quotations; only the
  ids differ (`s`, `m`, `c`). The 22 round-7 requests yield the same items and constraints.
- Before the fixes of design sections 20.4 and 20.5, the replayed round 7 named 8 of the 15 STEM
  mutations and 6 genuine STEM receipts (cs-t13, maa-p7b, maa-t13, mai-t13, ph-p7b, ph-t13) carried
  false INT-SUBJ-001 errors; each cause is fixed in the reading and pinned by a test
  (`tests/stem/test_round7_false_errors.py`, `tests/stem/test_round7_mutations.py`).
- Suite on the merged tree: 4353 passed, 45 deselected (stress), 4 xfailed, no failures, in 122 s;
  `scripts/arena/test_arena_rules.py`: 27 passed.

### 10.2 STEM repair 1, measured on the recorded rounds

An independent test of the overseer's STEM completion planted STEM faults the front end did not
read (design section 21). After the repair, the harness on fresh copies of every recorded round
gives the merge's functional counts: r1 30/30, r1-adv 150/151, r2 to r6 46/46 each, r7 177/177.
Compared record for record with the tree before the repair (status, functional, every finding's
code, severity and claims, every outcome, every formal check), r1 to r6 are identical, and on r7
39 records of eight STEM answers differ only as the new readings say:

- 96 formal checks added, every one ENTAILED, none removed: bi-t13 four `giv` checks of its table
  values and ess-t13 two (rule `table-data`), ph-t13 five `res` checks (four named changes and the
  inline restatement "16.4 W, so 16 W"), ph-p7b the decay line in counts min⁻¹ (`stem-eq-9`), on
  each of their variants;
- ph-p7b's word count reads "counts min⁻¹" after a number as the unit of its line of working, not
  as prose: on the genuine answer "measured 177 words (prose only: 45 words of working excluded …)"
  for 191 and 62 before, and 14 prose words fewer on each of its variants, against the bound of
  300 (ENTAILED throughout);
- every check's `detail` and failure message carries the corrected short form of the tolerance
  rule; every STEM mutation is named by the same codes on the same claims.

No status and no functional count changed, and no genuine receipt gained a finding. These are
replays of recorded answers: no specialist was called.

### 10.3 STEM repair 3, measured on the recorded rounds

A third independent test of the overseer's STEM completion found a false error on correct work (a
value stated under a condition read as a unit conversion), an arithmetic slip passed inside a
stated uncertainty, and fault forms the front end did not read (design section 23; STEM repair 2's
measurements are `docs/OVERSEER_RESULTS.md` section 19). After the repair, the harness on fresh
copies of every recorded round gives the merge's functional counts: r1 30/30, r1-adv 150/151, r2 to
r6 46/46 each, r7 177/177. Compared record for record with the tree before the repair (every field,
identifiers and times folded), r1 to r6 are identical, and on r7 the 8 records of ph-p7b differ only
as the new readings say:

- 16 formal checks added, every one ENTAILED, none removed: on each of ph-p7b's eight records, the
  time "32 h is 4 half-lives" as four times its T½ = 8.0 h, and the power (1/2)⁴ written after it
  against the 4 (rule `half-lives`);
- no status, functional count or finding changed, and no other recorded STEM answer gained or lost
  a check: the 15 STEM mutations are named by the same codes on the same claims.

These are replays of recorded answers: no specialist was called.

### 10.4 STEM repair 4, measured on the recorded rounds

A fourth independent test of the overseer's STEM completion found two false errors on correct work
(a Boolean expression evaluated under the values its statement gives, read as an identity; a later
part's substitution of the value a stated change ends at, set against the earlier binding), a Given
uncertainty written "±3%" neither checked nor named, a 12% slip passed through a rounding interval
on exact working, and fault forms the front end did not read (design section 24; the overseer's
measurements are `docs/OVERSEER_RESULTS.md` section 21). After the repair, the harness on fresh
copies of every recorded round gives the merge's functional counts: r1 30/30, r1-adv 150/151, r2 to
r6 46/46 each, r7 177/177. Compared record for record with the tree before the repair (every field,
identifiers and times folded), r1 to r6 are identical, and on r7 23 records of three STEM answers
differ only as the new readings say:

- 92 formal checks added, every one ENTAILED, none removed: six on each of ess-t13's six records
  (its values at sites A to E, rule `row-value`) and seven on each of ph-p7b's eight (the
  uncertainties it writes with its corrected rates, each 2% of the measured value, rule
  `stated-uncertainty`);
- on each of maa-p7b's nine records the quoted "0.693/8.0 h = 0.087 h⁻¹" is decided in Form E
  instead of Form S (ENTAILED for SATISFIABLE: its 8.0 carries the exact T = 8 of part (b), rule
  `exact-carry`), and holds as before;
- no status, functional count or finding changed, and no other recorded STEM answer gained or lost
  a check: the 15 STEM mutations are named by the same codes on the same claims.

These are replays of recorded answers: no specialist was called.

### 10.5 STEM repair 5, measured on the recorded rounds

A fifth independent test of the overseer's STEM completion found four false errors on correct work
(the evaluation of a formula after its correct rearrangement read as a step from it; a symbol
reused in a part for another quantity set against the other part's value; a count after "so"
paired with a chain three statements before), a relation the prose gives as a quantity's value
neither checked nor named, a conversion and a rounded restatement written in prose missed, and a
false warning on 2% of a raw table cell (design section 25; the overseer's measurements are
`docs/OVERSEER_RESULTS.md` section 22). After the repair, the harness on fresh copies of every
recorded round gives the merge's functional counts: r1 30/30, r1-adv 150/151, r2 to r6 46/46
each, r7 177/177. Compared record for record with the tree before the repair (every field,
identifiers and times folded), every round is identical, r7 included: no recorded STEM answer is
written in a shape the new readings read, so none gains or loses a check, and the 15 STEM
mutations are named by the same codes on the same claims. The front end's own dump of every check
(its status, severity and description) and every finding on the nine recorded round-7 STEM answers
(96 checks, 33 findings) and on the 558 labelled corpus items (1,918 checks, 102 findings) is byte
for byte the same before and after the repair. Measured 2026-10-23, after the repair's third pass.

These are replays of recorded answers: no specialist was called.

### 10.6 STEM repair 10, measured on the recorded rounds

A tenth independent test of the overseer's STEM completion found a wrong conversion in prose checked only at the end of
the answer (its clause's end read in a window of the whole text), a line's column taken from its part's question, values
at a supplied table's row restated wrongly in common shapes, another resistor's value substituted for the one a sentence
names, a wrong law evaluated right at a condition its part had computed, a base conversion in prose and a definite
integral named by nothing, a slip under 1/100 on the request's exact data held, and a value restated from a decimal written
with its digits cut left undecided (design section 30; the overseer's measurements are `docs/OVERSEER_RESULTS.md`
section 27). After the repair, the harness on fresh copies of every recorded round gives the merge's functional counts: r1
30/30, r1-adv 150/151, r2 to r6 46/46 each, r7 177/177. Compared record for record with STEM repair 9's run (every field,
identifiers and times folded), r1 to r6 are identical, and on r7 the 23 records of three STEM answers differ only as the
new readings say:

- 55 formal checks added, 46 ENTAILED and 9 SATISFIABLE, none removed: on each of ess-t13's six records the two counts
  of part (b), "the most nymphs (34)" and "only 9" (rule `row-value`); on each of maa-t13's eight the two evaluation
  brackets of part (c), `[3t² − t³]₀² = (12 − 8) − 0` and `[3t² − t³]₂³ = (27 − 27) − (12 − 8)` (rule
  `definite-integral`); on each of mai-t13's nine the restatement of its cut value `4787.58\ldots` as `4788` euros, to the
  nearest euro, the place of that restatement (rules `ellipsis-rounding` and `rounded-digits`), and the computed value
  `\dfrac{\ln 1.5}{\ln 1.003}` against `135.36\ldots` (SATISFIABLE, a value of logarithms in Form S);
- 25 ST-UNDEC-001 warnings removed, each now a check: maa-t13's two evaluation brackets (16) and mai-t13's cut value's
  restatement (9); the integral of v, which is no polynomial, and mai-t13's power beyond 12 keep theirs;
- no status, functional count or code set changed, and the 15 STEM mutations are named by the same codes on the same
  claims.

The STEM front end's own dump on the nine recorded round-7 STEM answers goes from 96 checks and 33 findings to 103 and 30
(the seven checks and three removed warnings above), and on the 558 labelled corpus items from 1,918 checks and 102
findings to 1,924 and 96: math-calc-2, stem-math-013 and stem-math-014 each gain a definite integral checked against its
evaluation bracket and the bracket at its limits, both holding, in place of two ST-UNDEC-001 (math-calc-2's gold, which
listed its integral as undecided, lists the two checks). Measured 2026-10-24.

These are replays of recorded answers: no specialist was called.

### 10.7 STEM repair 11, measured on the recorded rounds

An eleventh independent test of the overseer's STEM completion found correct working failed in exact mode when the result
is a rounded quotient of whole numbers, a Given one unit off the request's data accepted, part (b)'s factorisation and
roots in a letter part (a)'s question gives a value unchecked, a function's value in prose, a wrong restatement of an
inequality's solution, a wrong derivative, a wrong given substituted where no symbol is bound and a base phrase opening the
clause named by nothing (design section 31; the overseer's measurements, the knowledge pack's modules among them, are
`docs/OVERSEER_RESULTS.md` section 28). After the repair, the harness on fresh copies of every recorded round gives the
merge's functional counts: r1 30/30, r1-adv 150/151, r2 to r6 46/46 each, r7 177/177. Compared record for record with STEM
repair 10's run (every field, identifiers and times folded), r1 to r6 are identical, and on r7 the 17 records of two
STEM answers differ only as the new readings say:

- 58 formal checks added, 39 ENTAILED, 18 SATISFIABLE and 1 COUNTEREXAMPLE, none removed (the planted slip of maa-t13's
  `stem_arithmetic_slip` mutation keeps its failing check, renumbered): on each of maa-t13's eight records the derivative
  `a = dv/dt = 6 − 6t` against the one the power rule forms from the request's v(t) (rule `derivative`, a warning check),
  part (b)'s factorisation `3t(2 − t) = 0` as a step from `6t − 3t² = 0` and its roots `t = 0`, `t = 2` and `t = 0 or t =
  2` (rules `part-condition` and `root-statement`); on each of mai-t13's nine the two restatements `12n > 135.36…, so n >
  11.28…` against the relation before them solved exactly (rule `inequality-solution`, SATISFIABLE: a value of logarithms
  in Form S). The one failing check is on the injected claim of maa-t13's `stem_substitution` mutation, whose planted
  `a = dv/dt = 6 − 3t` now also fails the power rule's check (INT-SUBJ-004, a warning) beside the INT-SUBJ-001 it was
  named by;
- 26 warnings and notes removed: maa-t13's ST-SCOPE-001 note that t is rebound in part (b) (eight; t is part (b)'s
  unknown now) and mai-t13's two ST-UNDEC-001 on the restatements with an ellipsis (eighteen, each now a check);
- no status, functional count or naming changed: the 15 STEM mutations are named by the same codes on the same claims,
  and no record has an unexplained finding.

The STEM front end's own dump on the nine recorded round-7 STEM answers goes from 103 checks and 30 findings to 110 and
27 (the seven checks and three removed findings above, on the genuine answers), and on the 558 labelled corpus items from
1,924 checks and 96 findings to 1,934 and 91: math-calc-1, math-deriv-1 and a mutant of each gain their derivative checked
by the power rule and holding (four ST-UNDEC-001 gone), stem-math-011 its derivative and the value its equation step solves
for (one ST-UNDEC-001 and its ST-SCOPE-001 gone; its stationary point keeps its own), probe-M3-calculus-err and
stem-math-012 the planted wrong derivative failing on its claim, mai-func-1 its function's value and stem-phys-030 the
place its stated rounding names, all holding but the two planted derivatives. Measured 2026-10-24.

The stress targets of section 5 (`-m stress`, run alone after the suite): four of five pass; the adversarial
400,000-character mix took 1.56 to 1.66 s at best of five in three runs against its 1.5 s target, on a machine slower
that day than at STEM repair 10 (the file's run 57 to 61 s against 53 s, the mix 1.475 s then). The tree before the
repair, run the same way at the same times, took 1.61 and 1.65 s, and timed alone, the two trees alternately, the mix
takes 1.41 to 1.60 s before and 1.42 to 1.60 s after (best of five each time): this repair's readings add about 15 ms of
it, within the machine's noise. The target is left as it is.

These are replays of recorded answers: no specialist was called.

### 10.8 STEM repair 12, measured on the recorded rounds

A twelfth independent test of the overseer's STEM completion found a wrong derivative ENTAILED and satisfied with no
finding (an identity's variable took the request's value, so the identity was decided at that value only), hexadecimal
restatements with letter digits in prose and restatements after an approximation word named by nothing, and a circular
translation in affine or scaled form named by no check (design section 32; the overseer's measurements are
`docs/OVERSEER_RESULTS.md` section 29). After the repair, the harness on fresh copies of every recorded round gives the
merge's functional counts: r1 30/30, r1-adv 150/151, r2 to r6 46/46 each, r7 177/177. Compared record for record with
STEM repair 11's run (every field, identifiers and times folded), every round is identical, r7 included: no formal check
is added or removed, no status, functional count, code or naming changes, and the 15 STEM mutations are named by the same
codes on the same claims: on the recorded answers the new readings add no check and change no outcome.

The STEM front end's own dump on the nine recorded round-7 STEM answers stays at 110 checks and 27 findings, every status
the same; only maa-t13's two recorded antiderivatives (`∫6t dt = 3t²` and `∫3t² dt = t³`, both holding) state what they
compare now, their variable named. On the 558 labelled corpus items it stays at 1,934 checks and 91 findings, every
status the same; six restatements after an approximation word (in stem-bio-004, stem-phys-029, stem-phys-034,
ess-doubling-1 and its power-of-ten mutant, and ess-doubling-2) state in their detail the τ of 0 they were always banded
with. Measured 2026-10-24.

The stress targets of section 5 (`-m stress`, run after the suite and twice more, the trees before and after the repair
alternately): three of five pass, both trees alike, on a machine other work kept loaded that day (a load of 7 to 8 on four
cores). The typical answer's p95 receive took 312 to 333 ms after the repair and 333 to 337 ms before (target 250 ms), and
the adversarial 400,000-character mix 2.06 to 2.32 s at best of five after and 2.30 and 2.41 s before (target 1.5 s, missed
at STEM repair 11 too, 1.56 to 1.66 s); timed alone, the two trees alternately, the mix takes 1.96 and 2.11 s after and
2.00 and 2.12 s before. The targets are left as they are.

These are replays of recorded answers: no specialist was called.

### 10.9 A live integrated round

*No results yet.* The integrated arena merges `stem-build` (round 7 when the merge is ready,
otherwise round 8) and tests STEM with a STEM lens and a STEM fixer, using real STEM specialists
on the cheapest model tier, each configured only from its own v4 knowledge base (full-context
bundle), with no MyLib or textbook library. Record each round here, from measured results only:

- the round, the merged revision and the specialists that answered (by subject);
- the answers received and the STEM mutations injected and named, by kind and expected code;
- errors on genuine answers, each with its receipt, and whether the STEM lens judged it a true
  fault or a false error;
- relations named undecided on genuine answers, by reason and subject;
- notations or readings the specialists used that the front end did not read;
- the STEM fixer's fixes, each with the test that pins it, and the suite after them.

### 10.10 The round-7 arena's STEM findings, measured on the recorded round

After the fixes of design section 34 the harness on a fresh copy of the recorded round 7 gives 177 of 177 functional, as
before, and compared record for record with a run of the tree before the fixes (on another fresh copy), every formal check,
status and STEM finding of every record is the same: on the recorded answers the new readings add no check and change no
outcome. Each finding's probes now give the expected verdicts (`tests/stem/test_round7_arena_fixes.py`, 79 tests). Measured
2026-10-25 on a machine other work kept loaded (load 7 to 10).

These are replays of recorded answers: no specialist was called.
