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
  res giv tgt chem bool tt base`). They are planned here, so the parser's claim assumptions and the
  pack's checks agree. A planned check that the `checks` stage cannot encode keeps its id: the
  undecided finding names it.
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
| `numbers.py` | `ExactNumber` (value, significant figures, last place, half-width, exactness, exponent), the one number scanner `scan_number`, based numerals `scan_based` |
| `units.py` | unit table, prefixes (a Latin prefix before a Greek unit symbol too: `kΩ`, `MΩ`, `mΩ`), dimension vectors, unit-expression parser, ambiguity readings, exact SI factors; the English words that are no units after a number (`as`, `am`, `at`); bits, bytes and the binary multiples; the parts of a compound quantity (`compound_part`: `4 min 30 s`) |
| `lexer.py` | single-pass tokenizer (plain and LaTeX modes); unknown LaTeX commands and confusable letters become `ERROR` tokens; a combination or permutation count (`⁵C₂`, `5C2`, `nCr`, `C(5, 2)`, `₅P₂`) is one `UNSUP` token; the integer operators `mod`, `modulo`, `div` between operands, `//`, `\bmod` and, in Computer Science, `%`, the AND dot (`A.B`) and a numeral in groups of four digits with its base subscript (`1011 0110₂`); a superscript run beyond the numeral bound is never converted (ST-LIM-001) |
| `nodes.py` | frozen AST nodes (`IntOp` for an integer remainder or quotient) and helpers (`walk`, `symbols`, `align`, `render`, `shape_key`, `value_of`, ...) |
| `parser.py` | bounded Pratt parser: chains, connectives, units, implicit multiplication against scope (at most two readings), unsupported constructs as named nodes; a quotient stated with its remainder and a congruence `a ≡ b (mod n)` |
| `spans.py` | code, LaTeX display and inline, chemical equations, prose math runs, verbal arithmetic, quantities, tables, data lines, part labels and markup |
| `layout.py` | the round-7 layout rules restated from the generic parser (part labels, label-only lines, mark annotations, joined lines, table rows; docs/STEM_DESIGN.md, section 20.1) |
| `segment.py` | statements: the shared sentence splitter on the prose view plus the STEM boundary rules; derivation lines (an equation continued on lines opening with `=` is one), display rows, list items, code blocks, one statement per table row |
| `scope.py` | name pre-pass, bindings with provenance, formulas, rebinding notes (ST-SCOPE-001) |
| `chem.py` | chemical species and equations (structure only; balance is decided by the engine) |
| `boolean.py` | Boolean expressions (AND, OR, NOT, XOR and the gates NAND, NOR, XNOR; a gate's order with no brackets is ST-PARSE-002), truth tables |
| `relations.py` | link classification, sequence steps and roots, results (with rules `rounding-cue`, `inline-restatement` and `restated-binding`), givens of every kind and targets (rules `given-kinds` and `named-given`, ST-UNDEC-003), the start of a named change (`named-change`) and values taken from a supplied table (`table-data`, `table-operands`), dimension and unit findings (with rule `bare-factor`), the statements a substitution contradicts (`related-statements`), questions (`question`), relations written partly in words (`fragment`) and steps after a premise word (`premise-cue`), check planning and ids |
| `calculus.py` | polynomials in one variable and the power rule, for the antiderivative check (the derivative is the pack's, the identity the engine's; section 20.5) |
| `models.py` | exponential models (`P = P₀e^(kt)`, `C(t) = C0 e^(−kt)`, `A(t) = 500 × 2^(t/3)`), their applications (the model's letter glued to its bracket) and the polynomial exponents a `mod` check reads through positive variables (docs/STEM_DESIGN.md, section 33, item 5) |
| `datatables.py` | the pipe tables of the texts supplied with a request (header names and units, the first column the key; bounded) |
| `document.py` | `StemDocument` and the memoised `build_document` (`data`: the supplied texts' tables, when the caller has them); rule `unread-relation` (a relation sign between maths that no span reads is ST-PARSE-001) |

The later stages added these modules to the same package (still importing nothing from
`branches/`, `channel/`, `engine/` or `ir/`):

| Module | Stage | Role |
| --- | --- | --- |
| `constants.py` | `checks` | data-booklet constants: a written constant widens to its booklet value (D3a); an unstated standard symbol may take it at warning severity (D3b) |
| `enclosures.py` | `checks` | the exact-value table and rational enclosures for π, e and the functions, cross-checked against `math` |
| `scaling.py` | `checks` | decimal-exponent factoring, so literals stay within the IR's 40 digits |
| `tolerance.py` | `checks` | the STEM tolerance rule (R1 to R10), its short form, the scope statement `STEM_SCOPE`, the band builders; an approximation word as a whole word directly before what it qualifies (`approx_word_before`; the front end reads it too) |
| `to_ir.py` | `checks` | AST to IR 1.0 data, one allowlisted node at a time; symbol naming and premise groundings |
| `checks.py` | `checks` | `build_checks`: a `PlannedCheck` (an IR problem) per planned check, or an ST finding naming it undecided |
| `si_reading.py` | `branch` | the SI reading of `quant` and `CorePack` (`SI_READING`) and its views |
| `hub_hooks.py` | `branch` | the STEM hub hooks (`STEM_HOOKS`): imperatives, coverage words, echo exemption, word-count view |

`ENCODINGS.md` describes the checks stage; `branches/README.md` and the top-level `README.md`
describe the STEM branches end to end, with a worked example.

## Bounds (all in `StemLimits`)

Response 400,000 characters; math span 2,000 characters; 400 tokens per span; 12 links per chain; 30 written digits in a
superscript run (beyond it ST-LIM-001 on the span, before any conversion);
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
the 400,000-character response bound under `-m stress` (each under two seconds when measured).

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
condition or unit (docs/STEM_DESIGN.md, section 33, item 4); it binds nothing. The front end reads
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

`test_stem_repair1` pins the readings STEM repair 1 added (docs/STEM_DESIGN.md, section 21), each
with a clean control: prefixed Greek units and the English words that are no units, `counts`,
rule `bare-factor`, combination and permutation counts, rules `rounding-cue` and
`inline-restatement`, request quantities named in words, rules `named-change`, `table-data`
(`datatables.py`) and `related-statements`, end to end through the hub where a receipt is
involved. `test_stem_repair2` pins the readings STEM repair 2 added (section 22), each with a clean
control: integer arithmetic and its encoding, verbal arithmetic read once, rules `fragment`,
`unread-relation` and `question`, every kind of Given (rules `given-kinds` and `named-given`,
ST-UNDEC-003, zero and booklet constants, unreadable Givens), rule `table-operands`, rules
`restated-binding` and `exact-carry`, asides and premise cues, and every recorded round-7 answer
free of a failed new check or a new ST code. `test_stem_repair3` pins the readings STEM repair 3
added (section 23), each with a clean control: rule `value-at` (a value stated under a condition,
never a conversion), rule `central-value`, rule `processed-data` with its reprocessing and ratio
controls, rules `supplied-values`, `given-digits` and `given-uncertainty`, header units with ASCII
exponents and units written "per", rule `restated-unit`, rules `percentage-change` and
`half-lives`, a stated rounding of a stated value, a percentage never restating a quantity, and
every recorded round-7 answer free of a failed new check. `test_stem_repair4` pins the readings STEM repair 4
added (section 24), each with a clean control: rule `boolean-values` (an evaluation under stated
values, never an identity, and a statement that says more than the values setting nothing up),
rule `changed-value` (in the change's part or after it, never an earlier part), rule
`given-uncertainty` for "±", "+/-" and "%", a Given with its uncertainty after its symbol's
formula, a Given of a span not read whole, rule `rounding-cue` with a unit word or a part of the
unit ("to the nearest cent"), rule `row-value`,
rule `exact-carry` for exact working, rules `stated-uncertainty` and `operand-precision`, and
every recorded round-7 answer free of a failed new check. `test_stem_repair5` pins the readings
STEM repair 5 added (section 25), each with a clean control: rule `rearranged-formula` (a
rearrangement solved for another symbol or for none, never making the formula's evaluation a
step), rule `part-value` (a reused symbol matching its part's own result, with or without a lone
head, or a result its part computes), rules `inline-restatement` and `adjacent-restatement`, rule
`bound-relation` (a prose relation in stated symbols checked, a symbol with no value named, an
equation its part solves or that concerns its part's own result left unread), a spaced "×" before
a symbol read as a product, rule `prose-conversion` (with a verb, in brackets), rules
`rounding-cue` for a value stated for a symbol and `same-place` (a precision in brackets, the full
stop of "s.f."), rule `processed-data` for a percentage or a ratio of the raw cell, the per cent
read as its fraction, the second pass over the same classes (a rearrangement after "Making R the
subject", "Solving for R" or "Transposing" as a step, the verbs "equal", "is equal to" and "is
given by", conversions after "which equals", a semicolon or a dash before "that is", "converts
to" and a comma with "about", and the raw cell processed inside the line, a share of it in any
arithmetic form and the bounds of the measured value left unread), the third pass (a
rearrangement in any words before the formula's evaluation checked as a step from the formula,
the inverse's swapped equation no step, a reused symbol taking a value its part's prose names
otherwise, another part's value of the line's quantity or a computation in its place, a prose
relation giving its part's asked quantity in a reused symbol unread, no older chain restated after
a value following its own statement's value or a part of it, a prose value restated with a stated
rounding and a conversion to a unit the prose names checked, a ratio of the raw cell to its
processed value and a line naming the measured quantity unread, a ratio set against a number
named ST-UNDEC-001, an applied symbol no definition makes a function named ST-UNDEC-002), and
every recorded round-7 answer free of a reading of this repair. `test_stem_repair6` pins the
readings STEM repair 6 added (section 26), each with a clean control: rule `prose-given` (every
value of a data list whose head ends with a colon, of the list a "Given:" line opens and of a
Given clause's first clause, named by its item's words and checked as the same Given written with
"=", rule named-given in prose, a condition, a result after the first comma, "Data" with no colon,
an amount and a thousands group never read, a kind the request states no value of named
ST-UNDEC-003), rule `part-given` (a reused symbol given a request value its part's question and
working do not name, checked at warning severity in a check of its own; the part's own value and
one its working names first read with no check), rule `fraction-unit` (the unit after a compact
fraction read as the fraction's own when that gives the relation one dimension; a spaced slash,
"÷" and an agreeing divisor keep the divisor's), rule `boolean-gates` (NAND, NOR and XNOR and the
symbols ↑ ⊼ ↓ ⊽ in identities, evaluations and truth tables, a gate's order with no brackets named
ST-PARSE-002), and every recorded round-7 answer free of a reading of this repair.
`test_stem_repair7` pins the readings STEM repair 7 added (section 27), each with a clean control:
rule `solved-law` (a line that gives a symbol a value right after a law stating it not on its own
evaluates the law solved for it by exact inverse operations, never an algebra step from it; a
symbol with no stated value set against the values substituted for it before; a symbol twice or
under a function, a law with no other symbol and a value solving a law whose other symbols are
stated read as before; ST-ALG-001 in mathematics for a principal root; a Given statement never a
step), rules `leibniz` and `prime-derivative` (every Leibniz form of any order and letter, and any
letter with primes applied to a bracket, named a derivative, ST-UNDEC-001, never failed; a
derivative's value set against the answer's own formula of it; differing orders, `d/t` and a
primed letter with no bracket no derivative), rule `finer-restatement` (a restatement finer than
the chain's value set against the chain's written arithmetic at warning severity, the check
against the chain's value unchanged; none when the rounding is no finer), and every recorded
round-7 answer free of a reading of this repair.
`test_stem_repair8` pins the readings STEM repair 8 added (section 28), each with a clean control:
rule `value-at` for a computing chain and rules `name-list` and `item-label` (a value a run
computes under a condition, after the list or the range that names it, or for a numbered item is
the named quantity's value, never a relation of the condition, the list's last value or the number:
the tester's seven false INT-SUBJ-001 and their shapes; a slip still named on its computation; a
conversion of the condition and a list with no computation read as before), rule
`condition-value` and rule name-list's check (the value of the condition's dimension the
computation takes against the condition, a term that is no listed value against the list, at
warning severity, every digit counting; nothing for an affine condition or two values), rule
`table-terms` (a value copied wrongly from the supplied table or a wrong background set against
the row's cell or the stated value, at warning severity; a computed cell, a bound and a factor not
read; the row of a line's result never its operands' row), rule `law-values` (a law its evaluation
does not follow set against the line at the values it puts in, paired by dimension, at warning
severity; the right law, a computed term and another relation planning no such check; a failed
substitution naming its law's statement first), rule `inline-restatement` with up to three
describing words before ", so", and every recorded round-7 answer free of a reading of this
repair.
`test_stem_repair9` pins the readings STEM repair 9 added (section 29), each with a clean control:
rule `part-answer` (a check line or a line naming another quantity at the end of a part is no
answer of the part, so a change stated from the part's result is set against its answer: the
tester's three false INT-SUBJ-004), rule `named-result` (the value a line gives a quantity the
request names, by its words, its label or a symbol the answer substituted the request's value
for, set against the request's value at warning severity; the request naming a quantity after a
preposition, and nothing before a preposition and an article), rule `given-function` (a Given of
a function's value at any number, or of a function, set against the request's function; one the
request cannot set named ST-UNDEC-003 with why; f, g or h applied to a number read as the written
arithmetic of the application; a Given of a function's value no equation a later line steps
from), rule `row-terms` (a term of a sum over a supplied row's repeats set against them; the
row's own trials in any order clean; two unaccounted terms not read), rule `decay-law` (a value
computed over a stated number of half-lives with no power of ½ set against the decay law; a
power of ½ left to rule half-lives), rule `statistics` (a median, mode, range or mean of listed
values or a supplied column formed and set against the stated value; another statistic, and a
mode the values do not have, ST-UNDEC-001; a row's value and a list named otherwise not read),
rule `rounded-digits` (the place a stated rounding names set against the place the value is
written to, a whole number's trailing zeros either way), and every recorded round-7 answer free
of a reading of this repair.
`test_stem_repair10` pins the readings STEM repair 10 added (section 30), each with a clean
control: rule `prose-conversion` (whether a restated value ends its clause read in its own
statement, so a conversion followed by another statement is checked), rule `table-operands` (the
column a line's own words name, when they name exactly one and the line takes a cell of it), rule
`row-value` (a value at a supplied row stated in its own clause in any order of row, column and
verb, a numbered row by its key unit, columns told apart by a number; a comparison, an operation, a
processed quantity, a part of a column's name with other words before it, a list of rows and a
value under a condition, a hypothesis, a target, a modal verb or a bound no cell), rule `table-data` (the column chosen in the value's own statement), rule `named-change` (a
change's own start under its own condition restating nothing), rule `named-component` (a working
naming a component by a request value set against it), rule `condition-result` (a value under a
condition set against the value computed for the symbol under the same condition), rule
`prose-base` (a whole number restated in another base, both bases written; a base named only
after the first numeral read both ways, either holding), rule
`definite-integral` (a polynomial in one variable between whole-number limits, signed and in plain
text too, set against its evaluation bracket or a closed value; a root, a function or a decimal limit
ST-UNDEC-001), rule `operand-precision` for given data (a numeral that writes a value the request
states taken as exact, so a slip on a power of the request's rate fails at τ = 0; a stated side of
rounded numerals adding their rounding), rule `ellipsis-rounding` (a value restated from a cut
decimal and a closed expression set equal or approximately equal to one on either side, "2.66…"
read as cut, not rounded; a cut value inside an expression, "0.333… × 3 = 1", and a symbol set equal
to one ST-UNDEC-001, never failed), and every recorded round-7 answer gaining only checks that hold.
`test_stem_repair11` pins the readings STEM repair 11 added (section 31), each with a clean
control: rule `exact-rounding` (exact work states a value of two or more significant figures to
its last written digit, every trailing zero counting, so a rounded quotient of whole numbers
holds and a whole computed value is still stated exactly; one figure keeps h = 0), rule
`result-rounding` (a rounding a line states for its own result, after it or before it in its
clause), rule `given-data` (the request's data and a Given restating them taken as written, for a
Given and a substitution alike; the answer's own computed values keep R7's band), rules
`part-condition` and `root-statement` (a letter a part's question gives a value is an unknown of
the other parts' equations; a root statement leaves the equation it solves as the relation the
next line steps from; each named in the step's detail), rule `function-value` (a function's value
stated anywhere against the function the request, at warning severity, or the answer defines),
rule `inequality-solution` (a solved bound against the relation before it solved exactly, its
cut values read as cut or rounded digits; a reversed direction failing as a step), rule
`derivative` (a polynomial's derivative in any notation against the one the STEM pack forms by
the power rule; a derivative set equal to a number where it is no constant, and of anything
else, ST-UNDEC-001), rules `same-shape` and `unbound-substitution` (a numeral where the answer's
other evaluation of the expression writes the request's value, and a value for a symbol the
answer substitutes the request's value for elsewhere, both warnings; a hypothesis, a derived
value and a symbol tied to no one quantity not read), rule `prose-base` (a base phrase opening the
clause), and no recorded round-7 answer failing any check.
`test_stem_repair12` pins the readings STEM repair 12 added (section 32), each with a clean
control: rule `identity-variable` (a derivative, an antiderivative, a definite integral's bracket,
a Given function and a factorisation decided for every value of their own variable, with or without
a request that gives it a value, the problem holding no binding or formula of it and the detail
saying so; a step from a stated relation still binding what it substitutes), rule `prose-base`
for numerals with letter digits (in computer science, where the words beside the numeral or a
base phrase opening the clause name base 16; letters no word names a base for, and small letters
alone, never read), for a numeral set equal to one whose base the words after it name and for a
base phrase opening the clause with no comma (two false failures on correct working before), rule
`inline-restatement` after an approximation word, a rounding verb, "approximately equal to" or in
brackets (τ 0 by R8, the detail naming the reading; a value after a prose quantity, not a chain,
read by the other readings), and no recorded round-7 answer failing any check.
`test_round7_arena_fixes` pins the fixes of the round-7 arena's STEM findings (docs/STEM_DESIGN.md, section 34), each with a
clean control: the reading as written only where the written units agree or a written factor converts them, exact integers
of Mathematics and Computer Science matching only themselves, no symbol standing for a coefficient its formula writes, the
Computer Science AND dot and fragments glued by a full stop withheld, the stated solution of simultaneous equations against
every equation of the system, approximation words as whole words right before the relation, degree and radian conversions
in radians, the degree reading of a trigonometric function where the text gives degrees, '±' roots banded on both branches,
roots on the line after their equation claiming the solution set, stated factorisations and expansions as identities,
chained and absolute inequality steps and nuclear equations named, bits and bytes, prose values naming another quantity no
restatement, substitutions in another unit of their dimension or with their conversion factor, compound quantities, a
bracketed per cent after a value, comparisons stated false checked negated, count nouns before a sign, numerals in nibbles,
and overlong superscript runs bounded.
