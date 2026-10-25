# stem: the STEM math front end and encodings (docs/STEM_DESIGN.md)

This README describes the front end (stage `core`); the modules of the later stages are listed
under "Modules".

A deterministic reading of what STEM specialists write (Physics, Chemistry, Biology, ESS, SEHS,
Design Technology, Mathematics AA/AI, Computer Science): equations and prose mixed, in LaTeX,
Unicode, ASCII and words. It turns an answer into a `StemDocument` that the later stages
(`checks`: AST to IR; `branch`: parser, pack, hub) read. **No text is ever evaluated**: a
single-pass lexer and a bounded Pratt parser over a closed grammar build frozen ASTs; nothing
calls `eval`, `exec`, `compile`, `sympify`, `parse_expr`, `pickle` or any library that evaluates
strings, and `tests/stem/test_front_end_safety.py` enforces it with an AST scan and an import
allowlist. This package makes no engine call and changes no engine or IR file.

```
text ─► reading view (1:1) ─► name pre-pass ─► spans ─► statements ─► lexer ─► parser ─► ASTs
     ─► scope (request bindings first) ─► relations ─► planned checks (stable ids, claim ids) ─► StemDocument
```

## API for the later stages

```python
from epinoic_logic.stem import build_document

doc = build_document(answer_text, request_text, "physics")   # memoised (LRU, 64 entries)
doc.statements          # Statement(id="s1.2", kind, start, end, part, continuation, spans)
doc.statement_text("s1.2")   # == answer_text[st.start:st.end]: claim texts are offset substrings
doc.items               # MathItem: one read span or display row: chains (ASTs), chem, booleans, table
doc.bindings            # symbol -> (Binding(value, number, unit, source, statement_id), ...)
doc.substitutions       # values substituted into symbols bound nowhere else (readings only)
doc.formulas            # symbol -> (Formula(expr, statement_id, source), ...)
                        # (models of one variable, P = P₀e^(kt), are kept apart in the scope: models.py)
doc.relations           # every recognised relation and its outcome (check/binding/formula/context/undecided)
doc.checks              # planned checks: Relation(check_id="stem-eq-1", kind, statement_ids, left, op, right, ...)
doc.findings            # FrontEndFinding(code="ST-...", severity, message, statement_ids, check_id)
doc.request             # RequestReading: request bindings, quantities, relations, show-that targets
```

* **Check ids** are `stem-<kind>-<n>` per kind in document order (kinds: `eq sub alg sol mod cnv cmp
  res giv tgt chem bool tt base`, and from the argument diagnosis `op` (a stated step operation,
  ST-STEP-001), `sys` (a stated solution of a system), `rnd` (a comparison made with a rounded value,
  ST-ROUND-001)). A unit companion (ST-UNIT-003) takes its check's id with `u` appended
  (`stem-eq-1u`). They are planned here, so the parser's claim assumptions and the pack's checks
  agree. A planned check that the `checks` stage cannot encode keeps its id: the undecided finding
  names it.
* **Claim ids** of a relation are the statements that hold its two endpoints (a chain continued on
  the next line names both lines).
* **Outcomes**: `check` (planned), `binding` (a value stated for a symbol; no check), `formula` (a
  law or definition; its truth is out of scope), `context` (a relation with no premise to check it
  against, such as the first line of a derivation or a domain condition), `undecided` (the ST code
  and reason are on the relation and on a finding). Nothing recognised is dropped silently.
* **Per-kind fields** of `Relation`: `sub` has `pairs` (symbol to the substituted subtree), `evaluate`
  and `unbound` (the checks stage takes a booklet reading or reports ST-UNDEC-002), `formula`; `alg`
  and step `cmp` carry the premise (`premise_left`, `premise_op`, `premise_right`, `premise_ids`),
  `explicit` and `principal_root`; `sol` carries `root_symbol`, `roots`, `complete`, `restricted`
  and the equation as premise; `res`, `giv` and `tgt` carry the compared value and `candidates`;
  `chem`, `bool` and `tt` carry the equation, Boolean relation or truth table.
* The front end emits **no error-severity finding**. Every error comes from an engine result in the
  later stages.

## Modules

| Module | Role |
| --- | --- |
| `limits.py` | `StemLimits` (every bound of section 4.9) and `StemProfile` (per-profile reading switches: chemistry, bare `M`, tonne, Computer Science, principal root) |
| `normalize.py` | reading view (1:1 character map) and masked views of the same length (prose view) |
| `numbers.py` | `ExactNumber` (value, significant figures, last place, half-width, exactness, exponent; `truncated` for a decimal with a glued ellipsis, whose half-width is a full unit in its last digit), the one number scanner `scan_number`, based numerals `scan_based` and `scan_grouped_based` (`1011 0110₂` is one numeral) |
| `units.py` | unit table, prefixes, dimension vectors, unit-expression parser, ambiguity readings, exact SI factors |
| `lexer.py` | single-pass tokenizer (plain and LaTeX modes); unknown LaTeX commands and confusable letters become `ERROR` tokens; a glued ellipsis (`2.084429…`, `\\ldots`) and a spelled-out scale word (`45 million`) belong to their numeral, `ⁿCᵣ` is an exact binomial coefficient, and in Computer Science the dot between two operands (`A.B`) is AND; an over-long superscript run is `NUMERR` (ST-LIM-001), never an `int()` |
| `nodes.py` | frozen AST nodes and helpers (`walk`, `symbols`, `align`, `render`, `shape_key`, `value_of`, ...) |
| `parser.py` | bounded Pratt parser: chains, connectives, units, implicit multiplication against scope (at most two readings), unsupported constructs as named nodes |
| `spans.py` | code, LaTeX display and inline, chemical equations, prose math runs, verbal arithmetic, quantities, tables (a block of `|` lines is a table only with a delimiter row or a truth-table shape; other bars are absolute values, norms or determinants), data lines, part labels and markup; a run reads a count before it (`4 categories − 1 = 3` is 4 − 1 = 3) and a compound quantity as a sum (`4 min 30 s` is (4 min + 30 s)) with its own tokens, and stops before a value restated in brackets (`0.870 (87%)`) |
| `layout.py` | the round-7 layout rules restated from the generic parser (part labels, label-only lines, mark annotations, joined lines, table rows; docs/STEM_DESIGN.md, section 20.1); emphasis markers are paired in one linear pass (`emphasis_spans`, the reading of `EMPHASIS_RE`; with the markdown helper's markers, backtick included, it reads `adapters.markdown.EMPHASIS_RE`) |
| `segment.py` | statements: the shared sentence splitter on the prose view plus the STEM boundary rules; derivation lines (an equation continued on lines opening with `=` is one), display rows, list items, code blocks, one statement per table row |
| `scope.py` | name pre-pass, bindings with provenance, formulas, rebinding notes (ST-SCOPE-001) |
| `chem.py` | chemical species and equations (structure only; balance is decided by the engine) |
| `boolean.py` | Boolean expressions, truth tables |
| `relations.py` | link classification, sequence steps and roots, results, givens and targets, dimension and unit findings, check planning and ids; the argument diagnosis of section 24 (ST-REF-001, ST-UNIT-003 companions, ST-STEP-001/002, ST-ROUND-001, ST-RANGE-001, ST-WORK-001, ST-GIVEN-002, ST-SCOPE-002) |
| `calculus.py` | polynomials in one variable and the power rule, for the antiderivative check (the derivative is the pack's, the identity the engine's; section 20.5) |
| `models.py` | exponential models (`P = P₀e^(kt)`, `C(t) = C0 e^(−kt)`, `A(t) = 500 × 2^(t/3)`), their applications (the model's letter glued to its bracket) and the polynomial exponents a `mod` check reads through positive variables (docs/STEM_DESIGN.md, section 21, item 5) |
| `document.py` | `StemDocument` and the memoised `build_document` |

The later stages added these modules to the same package (still importing nothing from
`branches/`, `channel/`, `engine/` or `ir/`):

| Module | Stage | Role |
| --- | --- | --- |
| `constants.py` | `checks` | data-booklet constants: a written constant widens to its booklet value (D3a); an unstated standard symbol may take it at warning severity (D3b) |
| `enclosures.py` | `checks` | the exact-value table and rational enclosures for π, e and the functions, cross-checked against `math` |
| `scaling.py` | `checks` | decimal-exponent factoring, so literals stay within the IR's 40 digits |
| `tolerance.py` | `checks` | the STEM tolerance rule (R1 to R10), its short form, the scope statement `STEM_SCOPE`, the band builders, and the phrase readers `exactness_phrase` and `rounding_phrase` (stated exactness or rounding, which set a check's tolerance policy) |
| `to_ir.py` | `checks` | AST to IR 1.0 data, one allowlisted node at a time; symbol naming and premise groundings |
| `checks.py` | `checks` | `build_checks`: a `PlannedCheck` (an IR problem) per planned check, or an ST finding naming it undecided |
| `si_reading.py` | `branch` | the SI reading of `quant` and `CorePack` (`SI_READING`) and its views |
| `hub_hooks.py` | `branch` | the STEM hub hooks (`STEM_HOOKS`): imperatives, coverage words, echo exemption, word-count view (a line of nothing but written arithmetic is one maths word) |
| `reference_data.py` | argdiag | the closed reference: `QUANTITIES` (symbol, profiles, quantity, dimension, SI unit, ambiguous-with) and `FORMULAS` (data-booklet laws as exact coefficient and term data), and the cue tables of the ST-* checks (extrapolation caveats, working cues, change markers, comparison phrases) |
| `reference.py` | argdiag | reading the reference: `fixed_quantity` (a symbol's quantity, only when unambiguous or decided by the result's unit or the request, with the dimension guard), booklet formulas and their dimensions, coefficient-free dimensions (`0.5mv²`, `mv/2`), unit scales and the as-written reading test of ST-UNIT-003 |
| `word_formulas.py` | argdiag (repair round 2) | the reading view of a word equation ("kinetic energy = 0.5 × mass × speed²"): the reference quantities' names are rewritten to their symbols in place, so the law is read as the formula it spells and checked against the booklet (ST-REF-002); nothing is evaluated |

`ENCODINGS.md` describes the checks stage; `branches/README.md` and the top-level `README.md`
describe the STEM branches end to end, with a worked example.

## Bounds (all in `StemLimits`)

Response 400,000 characters; math span 2,000 characters; 400 tokens per span; 12 links per chain;
256 nodes and depth 24 per expression (checked before each descent); integer powers |n| ≤ 12 (up to
1000 over a closed base with no unit, read as one value);
scientific exponent |e| ≤ 99; 30 written digits; 2 readings per expression and 4 per check; 8
bindings per symbol; 128 checks per report (ST-LIM-002 beyond); 1,024 math spans read per report
(ST-LIM-002 beyond); 512 statements (the rest merge into `s.tail`); 16 species per side and 999
atoms per species; truth tables of at most 5 inputs; 64 cached documents. Every scan is linear:
prose lines are lexed in bounded windows, brackets are matched in one pass, look-backs use fixed
windows, and coverage tests use a bitmap. `tests/stem/test_front_end_safety.py` holds adversarial
inputs (nested brackets, unclosed `$`, `1e1e1e`, 30- and 10,000-digit numbers, `10^10^10`, nesting
depth 500, confusable letters, malformed LaTeX, control characters, storms of relation signs,
fences, bars and species) to time bounds: about 20,000 characters each in the default run, and at
the 400,000-character response bound under `-m stress` (each under two seconds when measured). That
figure covers those adversarial inputs only: a 400,000-character answer made entirely of list items
is read in linear time but took about 5 s in the re-run review (25k characters 0.65 s, 100k 1.7 s;
the read stops at 512 statements, ST-LIM-002), so it is not among the under-two-second inputs.
Repair round 2 bounded the per-line work (an emphasis fast path, a no-marker path for the furniture
reader, an index of mark ranges for prose numbers, a first-character test before the relation-sign
reader, blanking and masking per line): a 400,000-character list answer now takes about 3.4 to 3.7 s on this machine
(100,000 characters about 1.1 s), still not under two seconds.

## Argument diagnosis (docs/STEM_DESIGN.md, section 24)

The named STEM diagnostics of `named.NAMED_CODES` are either front-end findings (ST-REF-001, ST-REF-002, ST-RANGE-001,
ST-WORK-001, ST-GIVEN-002, ST-GIVEN-003, ST-GIVEN-004, ST-SCOPE-002, ST-STEP-002 at info) or engine-decided checks whose `PlannedCheck.defect`
the STEM pack copies to `FormalCheck.defect` (ST-UNIT-003 companions: `stem_unit_error`; `op`: `stem_invalid_step`;
`rnd`: `stem_rounding_changes_conclusion`). Every one reads only the document, the request and the closed reference;
nothing is executed, and none turns a failed or undecided check into a pass. Each label, with its derivation, example
and clean control, is in docs/ARGUMENT_DIAGNOSTICS.md (section 3.4).

Repair round 2 (docs/STEM_DESIGN.md, section 24.12) widened the readings at their causes: a computation set out over
lines is one chain (`relations._repeats_head`; the gap guard reads it without the repeated head, `Relation.head_gap`); a
product of quantity letters written with spaces is a product (`spans._spaced_factor`); a symbol after a condition's value
heads its own equation (`spans._condition_head`); a law on a line of its own lends its coefficients to the traced unit
companion; a rearrangement substituted with the task's values binds its symbols to the request's quantities
(`checks._request_step_bindings`); roundings stated in words, comparisons in symbols and target statements are `rnd`
checks (`relations._worded_roundings`, `_compared_roundings`, `_target_roundings`, with the target tables of
`reference_data.py` and every value of the request's prose in `RequestReading.values`); a law with a subscripted head and
a trend stepped in arithmetic are read for ST-RANGE-001; labelled objects and phrases after the value tell quantities
apart for ST-SCOPE-002 (`relations._phrase_words`); the reference holds the Lincoln index and a dilution, solved for
each of its symbols, and physics pressure (79 quantities, 15 formulas, 102 booklet laws). The round's class fixes, each
with its positive and its clean control in `tests/stem/test_repair_round2_classes.py`: givens that cannot all hold
(ST-GIVEN-004: a law of uniform motion or a free fall the stated values break, `_overdetermined_givens`; two-set counts
that do not add up, `_set_counts`); one symbol rebound with nothing saying which object each value is about
(`_unlabelled_rebindings`: ST-GIVEN-002 against the value the request states, ST-SCOPE-002 for parallel values used
mixed, `_mixed_groups`; two values differ as written, `_distinct`); a model the request states, past the range it states
(`_request_law_ranges`), and in Mathematics a trend over the request's dated years (`_dated_years`); numbers a
substitution introduces for symbols bound nowhere else traced for the unit companion; the condition a request sets on a
value as a rounding target (`_request_condition`, `_predicate_said`), with the value before the rounding read in the
rounded value's unit (`checks._rnd`); two's complement numerals and Boolean evaluation chains (`_binary_literals`,
`boolean._chain_links`).

## What the front end does not decide

Whether a relation holds: every verdict on a stated relation is an engine result in the later
stages. A power with a non-integer exponent is read as one value (`RealPower`) only when its base
and its exponent are closed and carry no unit (`10^(−8.2)`); so is an integer power beyond 12, up to
1000, of such a base (`(1 + 0.065/12)^{-60}`, `1.003^{144}`). The later stages decide it exactly when
its value is rational and fits one literal (`16^{3/4} = 8`, `2^{20} = 1048576`) and otherwise through
an enclosure, and an algebra step that holds an enclosed power stays undecided. A symbolic power
(`10^(−pH)`, `e^(kt)`), and an integer power beyond 12 of anything else, stay undecided as values; a
power of e or of a positive closed base with an exponent in symbols keeps its base and exponent on
the node, and an equality that applies an exponential model of the answer or the request at an
argument (`P(t + 4) = P₀e^(k(t + 1))` after `P = P₀e^(kt)`) is planned as a `mod` check (the model's
letter glued to its bracket; written decimals, units and the model's own definition keep the old
reading; a letter defined as two models is read in each). No algebra step is read over an
application of a letter the text defines as a function (`N(10) = 200`, then `N(15) = 100`, after
`N(t) = …`): an evaluation at a value is no step, and a step at an unknown is ST-UNDEC-001. A unit exponent may be written in ASCII glued to its atom after a number (`3 m s-1`,
`1 mol dm-3`, `25 cm3`, `9.81 m/s2`); `300 K-273`, `5 m-3 m` and `2 m2` keep their reading. Digit groups
may be separated by `,`, a thin space or the LaTeX thin space `\,` (`21\,131.40`), in groups of
exactly three. A decimal the answer states in prose for a quantity it named by a symbol ("Let $M$ be
the monthly payment" … "Her monthly payment is €352.19") is planned as a stated root of the latest
equation in that symbol in the part (`stem-sol`), read only word for word and with no qualifier,
condition or unit (docs/STEM_DESIGN.md, section 21, item 4); it binds nothing. The front end reads
structure, records bindings with provenance and plans checks. It never
supplies a constant's value (data-booklet readings are the `checks` stage's, at warning severity),
never runs code (ST-CODE-001), and never reads a molar mass from a formula.

## Tests

`tests/stem/` has one file per module (`test_normalize`, `test_numbers`, `test_units`, `test_lexer`,
`test_parser`, `test_spans`, `test_segment`, `test_scope`, `test_relations`, `test_chem_parse`,
`test_boolean_parse`, `test_document`) and `test_front_end_safety`. The safety file holds:

* an AST scan of every module, with a meta-test that the scan catches each forbidden form;
* the import allowlist;
* the adversarial inputs.

`test_document` runs the labelled corpus (`tests/fixtures/stem/corpus`) and checks three things:

* every injected fault overlaps a planned check, an undecided relation or a named finding.
  The two exceptions are the prose relations that the `branch` stage reads (a per cent change
  and a doubling stated in words);
* correct answers carry no dimension, algebra, chemistry or parse warning;
* the observed case `stem-phys-001` plans `stem-eq-1`.

`test_segment` checks that importing and running the front end leaves the shared History
splitter's boundaries byte-identical.

Repair round 3 (docs/STEM_DESIGN.md, section 24.13): ST-STEP-003 (a rewrite inside a chain whose two sides differ at a
sample point of the unknown, `reference.difference_witness`); givens against a definition law (ρ = m/V,
`reference_data.DEFINITION_GIVENS_LAWS`) and against every uniform motion law they fix (ST-GIVEN-004); a rounding before a
comparison written with the symbol (the `rnd` check); missing working in Computer Science when the request asks for the
method in words, and for a "Show that" answered with the result alone (ST-WORK-001); a cancellation read as a division by
the unknown (ST-STEP-002); a percentage written once is one quantity (`reference.unit_written_once`).

Repair round 4 (docs/STEM_DESIGN.md, section 24.14): a temperature in °C or °F substituted into a law of the absolute
temperature is read in kelvin (`reference_data.ABSOLUTE_TEMPERATURE_LAWS`, `relations._kelvin_binding`), so the
unconverted substitution fails as a unit error; a numeral already written in SI is accounted for as that quantity
(`relations._si_form_binding`), so a time given in minutes or hours and used as written fails; a bare numeral for a
symbol the request states with an SI unit carries that unit, and π or e written as a rounded decimal aligns
(`nodes._rounded_constant`); an expansion or factorisation is checked as an identity under any request
(`relations._identity_shape`, `_cued_identity(shape_only=True)`, a warning). Tests: `tests/stem/test_repair_round4_stem.py`.

Repair round 5 (docs/STEM_DESIGN.md, section 24.15): a unit given only in the request is traced through the working
(`relations._unit_companion`), a given written inline in a substitution is read against the request
(`relations._inline_givens`), a conclusion drawn from a rounded value is read in its common shapes, adjacent quantity
letters are a product (`spans._quantity_run`, `parser._juxtaposable`), a symbol rebound to another dimension and used in
the first sense is a conflict (`relations._dimension_rebindings`), a reasoned proof of a property is no missing working,
unit homographs never continue a unit (`spans._UNIT_HOMOGRAPHS`), a count stated in a sentence binds N₀
(`checks._request_count`), and a '±' equation is two equations (`checks._sol`). Tests: `tests/stem/test_repair_round5_stem.py`.

Close round 1 (docs/ARGUMENT_DIAGNOSTICS.md, sections 3.4 and 12): a prose value of the other sign than its own
statement's chain states a magnitude and is no restatement (`relations._Planner._results`), and a value in prose is a
model's evaluation point only after an input cue and with no rate after it (`relations._INPUT_BEFORE_RE`,
`_RATE_AFTER_RE`). Tests: `tests/stem/test_close1_stem.py`.

Close round 2 (docs/ARGUMENT_DIAGNOSTICS.md, sections 3.4, 7 and 13): a Computer Science answer that writes a Boolean
constant with the AND dot (`lexer.writes_constant_dot`: "A.0", "(A + B).1") is read without the AND dot and without the
glued-dot guard of `checks._truncated_operand`, as before both readings, so a wrong step written that way is charged
again (DIFF-04); the committed base's reading of those full stops also charges a correct step written the same way, which
section 7 there records as given up. Tests: `tests/stem/test_close2_boolean_dot.py`.
