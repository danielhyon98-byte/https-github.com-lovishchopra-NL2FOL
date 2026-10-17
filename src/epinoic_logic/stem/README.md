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
doc.relations           # every recognised relation and its outcome (check/binding/formula/context/undecided)
doc.checks              # planned checks: Relation(check_id="stem-eq-1", kind, statement_ids, left, op, right, ...)
doc.findings            # FrontEndFinding(code="ST-...", severity, message, statement_ids, check_id)
doc.request             # RequestReading: request bindings, quantities, relations, show-that targets
```

* **Check ids** are `stem-<kind>-<n>` per kind in document order (kinds: `eq sub alg sol cnv cmp
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
| `units.py` | unit table, prefixes, dimension vectors, unit-expression parser, ambiguity readings, exact SI factors |
| `lexer.py` | single-pass tokenizer (plain and LaTeX modes); unknown LaTeX commands and confusable letters become `ERROR` tokens |
| `nodes.py` | frozen AST nodes and helpers (`walk`, `symbols`, `align`, `render`, `shape_key`, `value_of`, ...) |
| `parser.py` | bounded Pratt parser: chains, connectives, units, implicit multiplication against scope (at most two readings), unsupported constructs as named nodes |
| `spans.py` | code, LaTeX display and inline, chemical equations, prose math runs, verbal arithmetic, quantities, tables, data lines, part labels and markup |
| `layout.py` | the round-7 layout rules restated from the generic parser (part labels, label-only lines, mark annotations, joined lines, table rows; docs/STEM_DESIGN.md, section 20.1) |
| `segment.py` | statements: the shared sentence splitter on the prose view plus the STEM boundary rules; derivation lines (an equation continued on lines opening with `=` is one), display rows, list items, code blocks, one statement per table row |
| `scope.py` | name pre-pass, bindings with provenance, formulas, rebinding notes (ST-SCOPE-001) |
| `chem.py` | chemical species and equations (structure only; balance is decided by the engine) |
| `boolean.py` | Boolean expressions, truth tables |
| `relations.py` | link classification, sequence steps and roots, results, givens and targets, dimension and unit findings, check planning and ids |
| `calculus.py` | polynomials in one variable and the power rule, for the antiderivative check (the derivative is the pack's, the identity the engine's; section 20.5) |
| `document.py` | `StemDocument` and the memoised `build_document` |

The later stages added these modules to the same package (still importing nothing from
`branches/`, `channel/`, `engine/` or `ir/`):

| Module | Stage | Role |
| --- | --- | --- |
| `constants.py` | `checks` | data-booklet constants: a written constant widens to its booklet value (D3a); an unstated standard symbol may take it at warning severity (D3b) |
| `enclosures.py` | `checks` | the exact-value table and rational enclosures for π, e and the functions, cross-checked against `math` |
| `scaling.py` | `checks` | decimal-exponent factoring, so literals stay within the IR's 40 digits |
| `tolerance.py` | `checks` | the STEM tolerance rule (R1 to R10), its short form, the scope statement `STEM_SCOPE`, the band builders |
| `to_ir.py` | `checks` | AST to IR 1.0 data, one allowlisted node at a time; symbol naming and premise groundings |
| `checks.py` | `checks` | `build_checks`: a `PlannedCheck` (an IR problem) per planned check, or an ST finding naming it undecided |
| `si_reading.py` | `branch` | the SI reading of `quant` and `CorePack` (`SI_READING`) and its views |
| `hub_hooks.py` | `branch` | the STEM hub hooks (`STEM_HOOKS`): imperatives, coverage words, echo exemption, word-count view |

`ENCODINGS.md` describes the checks stage; `branches/README.md` and the top-level `README.md`
describe the STEM branches end to end, with a worked example.

## Bounds (all in `StemLimits`)

Response 400,000 characters; math span 2,000 characters; 400 tokens per span; 12 links per chain;
256 nodes and depth 24 per expression (checked before each descent); integer powers |n| ≤ 12;
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
and its exponent are closed and carry no unit (`10^(−8.2)`); the later stages decide it exactly when
its value is rational (`16^{3/4} = 8`) and otherwise through an enclosure, and an algebra step that
holds an enclosed power stays undecided. A symbolic power (`10^(−pH)`, `e^(kt)`) stays undecided. Digit groups may be separated
by `,`, a thin space or the LaTeX thin space `\,` (`21\,131.40`), in groups of exactly three. The front end reads structure, records bindings with provenance and plans checks. It never
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
