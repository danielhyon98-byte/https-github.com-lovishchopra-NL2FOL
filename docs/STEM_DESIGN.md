# STEM support: design

**Status: DESIGN, not implemented.** Branch `stem-build`. This document synthesises two
independent designs: the representation-outward design (R) and the fault-outward design (F).
R builds a math front end first and derives the checks from what it reads. F starts from the
faults the hub lets through today and builds an engine encoding for each. Where they
disagree, section 2 records the decision and the reason. Sections 17 and 18 split the
implementation into five sequential stages that touch disjoint files.

Evidence used here comes from read-only probes run against this worktree (baseline suite: 1067
passed, 12 deselected). The encodings in sections 5 and 7 were each run through
`engine.runner.verify`. Each took 4 to 20 ms. Forty arithmetic checks in a row took 327 ms.

---

## 1. Purpose and scope statement

The Epinoic logic translator turns what specialist agents write into IR that the Z3 engine
decides, so that no misstatement passes silently between agents (router, specialists,
combinator). STEM support is not a separate system. It is one more set of subject branches on
the same package (`epinoic_logic`), the same hub, the same channel and the same integrity
layer.

What STEM support must guarantee, for Physics, Chemistry, Biology, ESS, SEHS, Design
Technology, Mathematics (AA, AI) and Computer Science answers that mix equations and prose:

1. **Verbatim delivery.** What the router receives is what the specialist said.
   `original_response` is never altered. Every claim text is a substring of it, taken by
   offset. Code blocks, data lines and display maths become claims; they never vanish.
2. **Decided or named.** Every relation the front end recognises ends in one of three ways:
   - an engine check;
   - a finding that names it as undecided and gives the reason;
   - for a stated law or definition only: a relation recorded as context.
   Nothing recognised is dropped silently.
3. **Right code, right severity.** Every fault the infrastructure can see is named on the
   receipt with a stable code and a documented severity.
4. **No false errors.** Error severity comes only from an engine result about a relation that
   rests solely on what the report and the request state, or on exact encoding devices. If
   the reading or the tolerance could be wrong, the outcome is a disjunction of readings or a
   warning, never an error.

**Scope statement** (repeated in every STEM problem's `notes` and kept in every receipt
through `_SCOPE_TAIL`): a STEM check proves a property of its encoding only. It proves that
the written arithmetic, substitution, conversion, algebraic step, balance or Boolean identity
holds, or does not hold, under the stated premises, the documented readings and the STEM
tolerance rule. It does not establish any of the following:
- that a law applies;
- that data are true;
- that a model is physically valid;
- that a unit is the right one beyond the dimension and conversion checks named here;
- that the answer is what the question wanted.

The engine's `SCOPE_STATEMENT` applies unchanged.

**Observed today, and the target.** A Physics answer `a = (20 - 0)/4.0 = 6.0 m s⁻²` (true value
5.0) goes to the generic branch and crosses the hub ACCEPTED, with no finding and no formal
check.

Under this design the same answer:
- goes to the `sciences` branch;
- gets a `stem-eq-1` check that is a COUNTEREXAMPLE, with model `c = 5`, `r = 6`;
- receives INT-SUBJ-001 (error) naming the claim that holds the chain;
- is still delivered (ACCEPTED_WITH_FINDINGS).

Of 13 deliberately wrong probe answers, today only 1 has its equation error caught. The test
plan (section 16) requires every one to be caught or named.

---

## 2. Synthesis decisions (conflicts resolved)

| # | Point | R (representation-outward) | F (fault-outward) | Decision |
| --- | --- | --- | --- | --- |
| D1 | Linear or nonlinear | Allow nonlinear (`allow_nonlinear`) per check whenever a product of two unknowns appears. | Keep every check linear: substitute the stated value as a literal coefficient (`σ·s` for `s²`; plug in a stated root). | **Linear by default.** A check is nonlinear only when its encoding really multiplies two unknowns: exact surds, symbolic algebra steps, completeness of solution sets, and the interval form with two or more interval operands. F's literal-substitution trick is kept for exactly one job: a stated root is checked by substituting it into the equation (linear membership). It is not used as a general device, because it bakes the value under test into the coefficients and does not compose. |
| D2 | How the nonlinear policy reaches the engine | `FormalCheck.limits: Optional[Limits]`, any value allowed. | Not needed. | **A named policy, not raw Limits.** `FormalCheck.policy` is either `"linear"` or `"nonlinear"`. The engine maps the name to a fixed `Limits` (`engine/policies.py`), so a pack can never raise `max_nodes`, the digit count and so on. The engine records any non-default Limits on the signed result. |
| D3 | Constants (g, h, c, ...) | Never supply constant values. An unbound constant stays free, so the check is undecided. | Written constants match a disjunction of data-booklet values (`g ∈ {9.8, 9.81}`). | **A constants table, used two ways.** (a) A written literal that matches a table constant at its written precision may take any value from its rounding interval up to the booklet value. This only ever widens, so it cannot cause a false error. (b) An unbound standard-constant symbol may take its booklet value only when a dimension check against the stated result unit confirms that reading. Such a check carries `failure_severity="warning"`, so a failure is INT-SUBJ-004 (warning), never an error. Its premise is grounded `assumption`, so the engine lists it in `ungrounded_dependencies`. |
| D4 | Transcendental functions and π | Exact-value table only (special angles, powers of ten). Everything else is undecided. | Use π as an enclosure symbol; linearise square roots. | **Exact table plus enclosures.** Exact values (sin 30° = 1/2, log 1000 = 3) stay exact. Any other sin, cos, tan, arcsin, arccos, arctan, ln, log10 or exp of a closed argument, and π and e, become an enclosure symbol: a deterministic `Fraction` routine computes a rational interval of relative width at most 10⁻¹⁵. A check that uses an enclosure is decided in the interval form (D6), so it can never fail correct work. Square roots stay exact (an auxiliary symbol `s ≥ 0, s·s = x` under the nonlinear policy), so `√8 = 2√2` is proved, not approximated. |
| D5 | Tolerance | Half a unit in the last digit of S, plus a relative slack τ (1/100 for `=`, 1/20 for `≈`). The band is sign-aware and centred on the computed value. | The same band, `|s − k| ≤ h + τ·|k|`. | **Converged.** R's rules R1 to R9 are kept, with three grafts: constant intervals (D3), enclosures (D4), and decimal-exponent factoring (D7). |
| D6 | One form or two | Form E (entailment) when every operand is exact; Form S (satisfiability) when carried intermediates are present. | Entailment only, with a "computed" symbol pinned so the counterexample shows it. | **Both, by one rule.** If any operand has an interval reading (a carried intermediate, a constant, an enclosure), use Form S: is there an admissible reading under which the stated value holds? Otherwise use Form E, with F's pinned symbols `c` and `r`, so a COUNTEREXAMPLE prints the computed value beside the stated one. |
| D7 | Literal size (`max_const_digits = 40`; Planck's constant to 9 significant figures has 51 digits) | Report ST-LIM-001 and build no check. | Rescale by a power of ten. | **Factor out powers of ten exactly** (section 7.3). A product or quotient `E = M × 10^K` is compared as `|M − S·10^−K| ≤ h·10^−K + τ·|M|`. This is an exact identity, and K is integer bookkeeping on written exponents. ST-LIM-001 remains only when a literal still exceeds 40 digits after factoring. |
| D8 | Closed compound divisor | Auxiliary `q` with `q·b = a` and `b ≠ 0`; Python first refuses an exact zero. | The same (probed: `1/(1/4.0 + 1/6.0)`). | **Converged.** No validator change. Python never folds a divisor to a literal, so the engine decides the division. |
| D9 | Pack shape | One `StemPack(mode)`. | Separate Science, Maths and CS packs. | **One `StemPack(mode)`** with modes `sciences`, `mathematics` and `computer_science`, served by three branches. The front end is shared, so there is nothing to duplicate. Branch keys and parser agent ids keep the subjects apart on receipts. |
| D10 | Request text for formal checks | An optional method `formal_checks_for(report, request_text)`. | Pass `request_text` into `formal_checks`, or compare from `checks()`. | **Optional method.** `run_packs` calls it when a pack defines it, so the `IntegrityPack` protocol and every existing pack stay unchanged. |
| D11 | Claim roles | No new roles. Each statement's function lives in the shared document. | Not addressed. | **No new roles** (section 9). A new role would ripple through about ten enumerations for no gain. |
| D12 | Who rules on fault severity | An engine failure is always INT-SUBJ-001. | The same. | **Add `failure_severity` to `FormalCheck`.** A failure of a check that relied on a reading the report did not state is INT-SUBJ-004 (warning) instead of INT-SUBJ-001 (error). Such readings: a booklet value for an unstated symbol, a symbol's identity across request and answer, a show-that target, or a step that brings in symbols no stated relation connects. |
| D13 | INCONSISTENT_PREMISES | Not addressed. | Not addressed. | **Undecided for STEM checks** (`inconsistent_is_failure=False`). A STEM check's premises are encoding devices and earlier relations. If they are inconsistent, the fault lies in an earlier line (which its own check reports) or in a domain outside the encodings. Example: `x² + 4 = 0 ⇒ x = ±2i` is correct complex-number work, so it must not become an error. |
| D14 | Fault catalogue | Derived from the grammar. | The 13 silent passes and the false errors observed today. | **F's catalogue becomes the mutation corpus.** It is the acceptance bar for stage `corpus-eval` (section 16). |

---

## 3. Architecture

### 3.1 Flow from agent text to receipt

```
specialist text (verbatim)                         request text (router)
        │                                                   │
        ▼                                                   ▼
RouterHub.receive ──► BranchRegistry.for_subject(label) ──► branch sciences | mathematics | computer_science
        │                                     (generic stays the default for unrecognised subjects)
        ▼
StemTextParser.parse_response ──┐
                                │   one memoised StemDocument per (sha256(text), sha256(request) or "", profile)
StemPack.checks / formal_checks_for ──┤        stem.document.build_document()
CorePack(reading=SI_READING) ───┘          reading view ─► spans ─► statements ─► lexer ─► Pratt parser
        │                                  ─► AST ─► scope (givens, bindings, formulas) ─► relations
        │                                  ─► planned checks (stable ids, claim ids)
        ▼
claims (offset substrings, roles)     StemPack: plan ─► stem.checks ─► stem.to_ir ─► Problem (IR 1.0)
        │                                       └─► StructuralFinding ST-* (undecided, dimension, notes)
        ▼                                                   │
TranslatorChannel.respond: envelope · hand-off · request fidelity (echo and coverage hooks) · constraints
        │                                                   ▼
        │                 _branch_checks: verify(problem, config, limits=policy_limits(fc.policy), key)
        │                 status ─► satisfied True / False / None ─► INT-SUBJ-001 / -004 / -002
        ▼
TransmissionReceipt: status, findings (claim_ids named), structural_findings (ST-*), formal_checks
(ConstraintResult per check id, signed formal_result_id), summary (counts, failed and undecided ids, ST histogram, scope tail)
        │
        ▼
router (delivered unless an identity or integrity violation REJECTS it; STEM findings are content findings)
```

### 3.2 Principles

- **P1. One reading.** One deterministic front end turns the response into a `StemDocument`
  holding:
  - statements, with offsets;
  - math spans, ASTs and quantities;
  - the symbol scope;
  - classified relations;
  - planned check ids with their claim ids.

  The STEM parser (claims), `StemPack` (checks) and `CorePack` in SI reading (prose
  arithmetic, quotation reading) all read this one document. This extends the "one sentence
  splitter" rule of `branches/README.md`: claim ids, sentence numbers and check ids cannot
  diverge. The document is memoised in an `lru_cache(64)`.
- **P2. Text is data.** The front end is a hand-written scanner and a bounded Pratt parser over
  a closed grammar. Only allowlisted AST nodes are translated, and only into allowlisted IR
  1.0 nodes. Section 14 lists what is forbidden.
- **P3. The engine decides.** Python `Fraction` arithmetic only builds literals and refuses
  undefined encodings. It builds:
  - exact unit factors from the table;
  - half-widths from the written digits;
  - decimal exponents;
  - enclosure bounds.

  It refuses an exact zero divisor or the even root of a negative closed value. Every verdict
  on a stated relation is an engine result. The absolute value and the band are inside the IR
  (`ite`).
- **P4. Never silent, never over-flagged.** Ambiguity (unit symbols, implicit multiplication,
  as written versus SI) becomes a disjunction of at most 2 readings per expression and 4 per
  check, and correct work passes if any reading holds. If more readings would be needed, the
  relation is reported undecided (ST-PARSE-002). Ambiguity never becomes an error.
- **P5. STEM-scoped.** Every change of behaviour is reached only through the three STEM branches:
  - `StemTextParser`;
  - `StemPack`;
  - `CorePack(reading=SI_READING)`;
  - the STEM hub hooks.

  `CorePack()` with the default `GENERAL` reading runs today's code path byte for byte. English,
  History, Psychology, Economics, Business Management and generic are therefore unchanged. The
  shared edits in section 11 are additive, and their defaults reproduce today.
- **P6. The original is verbatim.** Normalisation happens only in a reading view of the same
  length, a 1:1 character map. Claim texts are offset substrings of the original, truncated to
  the contract (4000 characters).

### 3.3 Module layout

New subpackage `src/epinoic_logic/stem/`. It is the front end and the encodings, and it
imports nothing from `branches/` or `channel/`.

| Module | Role | Stage |
| --- | --- | --- |
| `limits.py` | `StemLimits`, a frozen dataclass holding every bound (section 4.9) | core |
| `normalize.py` | reading view (1:1 map) and prose view (math masked by same-length placeholders) | core |
| `spans.py` | code, LaTeX, Unicode or ASCII math runs, verbal arithmetic, derivation lines, data lines | core |
| `segment.py` | statements: sentences (shared `sentence_boundaries` on the prose view plus STEM boundary rules), derivation lines, display rows, list items, code blocks, part labels | core |
| `lexer.py` | single-pass tokenizer | core |
| `numbers.py` | `ExactNumber`: exact value, significant figures, last place, half-width, exactness, scientific exponent | core |
| `units.py` | unit table, prefixes, dimension vectors, unit-expression parser, ambiguity table, exact SI factors | core |
| `nodes.py` | frozen AST nodes | core |
| `parser.py` | Pratt parser; implicit multiplication resolved against scope | core |
| `scope.py` | symbol bindings with provenance; recorded formulas | core |
| `relations.py` | link classification and check planning (kinds, stable ids, claim ids) | core |
| `chem.py` | chemical formula and equation parser; element and charge tallies | core |
| `boolean.py` | Boolean expressions, truth-table blocks, base-2, 8 and 16 numerals | core |
| `document.py` | `StemDocument` and the memoised `build_document` | core |
| `constants.py` | data-booklet constants table (values, accepted written forms, units, profiles, ambiguous letters) | checks |
| `enclosures.py` | exact-value table; rational enclosures for π, e and the functions | checks |
| `scaling.py` | decimal-exponent factoring (section 7.3) | checks |
| `tolerance.py` | `STEM_TOLERANCE_RULE` text; band builders | checks |
| `to_ir.py` | AST to IR 1.0 (section 7) | checks |
| `checks.py` | `PlannedCheck` builder: Forms E and S, ids, descriptions, claim ids, policy, failure severity, truncation; ST findings | checks |
| `si_reading.py` | `SI_READING` for `quant` and `CorePack` (section 12) | branch |
| `hub_hooks.py` | STEM coverage terms, echo exemption, request imperatives, word-count view | branch |

Elsewhere: `adapters/stem_specialist/parser.py` (`StemTextParser`) and
`branches/stem_pack.py` (`StemPack`), plus the additive shared edits listed under stage
`branch` in section 17.

---

## 4. Math front end: grammar and bounds

### 4.1 Reading view (`normalize.py`)

The reading view is a 1:1 character map, so it has the same length as the original and
offsets are preserved:

- U+2212 (minus) becomes `-`.
- NBSP, U+2009 and U+202F become a space.
- U+00B7 and U+22C5 become a multiplication marker in math and unit context, and a hydrate dot in a
  chemical formula.
- U+00D7 `×` stays its own token.
- An en dash U+2013 is read as minus only after the start, a space, an operator, `(` or a
  relation sign, and before a digit or letter. `3–5 s` between two numbers is a range:
  Unsupported, named.
- Superscript digits and signs (⁰ to ⁹, ⁺, ⁻) and subscripts (₀ to ₉) are tokenised as they
  stand. Nothing is expanded.

The prose view masks every math span and every quantity carrying a unit with a placeholder of
the same length: an upper-case first character, then filler that is not a space, punctuation,
quotation mark or digit. The shared splitter can start a sentence at a masked span. It never
splits inside one, and it never sees a decimal point, prime, inch mark or quotation mark
inside one.

### 4.2 Spans (`spans.py`), extracted in this order

1. **Code.** Fenced ` ``` ` and `~~~` blocks (the language tag is kept), inline `` `code` ``,
   and 4-space indented blocks in the `computer_science` profile. A code span is recorded as a
   `CodeSpan`. It is masked from maths and prose, and it is never parsed for meaning or run.
2. **LaTeX display.**
   - `$$…$$` and `\[…\]`;
   - the environments `equation`, `equation*`, `align`, `align*`, `gather` and `gather*`.

   Rows are split at `\\`, and `&` is dropped.
3. **LaTeX inline.** `$…$` and `\(…\)`, following TeX convention: the content is non-empty,
   has no leading or trailing space, closes in the same paragraph, and is at most
   `max_span_chars` long. `\$` and an unclosed `$5 per kg` are currency.
4. **Unicode or ASCII runs in prose.** A maximal run the math lexer can tokenise that
   contains a relation sign. It starts at an identifier, a number, `(` or a minus. It stops
   before a prose word: three or more letters that are not a function name, unit word, Greek
   name or multi-letter symbol in scope. It also stops at sentence punctuation followed by a
   space and a capital.
5. **Verbal arithmetic.** `<number> (plus | minus | times | multiplied by | divided by)
   <number> … (equals | is equal to | gives | =) <number>`, with numbers only and no symbols.
   It is read as the same AST.
6. **Derivation lines.** A line (a newline inside a paragraph) is a derivation line when at
   least 60 % of its non-space characters lie in one math run. A line that begins with a
   relation sign continues the previous line's chain.
7. **Bracketed data, vector and list lines** (`[1, 2]`, `{2, 3}`, `(x, y) = (3, 4)`) and
   Markdown tables become text claims. A truth-table block (section 4.8) is recognised from a
   header row and rows of 0/1 or T/F. A JSON receipt shape (string keys) keeps the shared JSON
   rule.

### 4.3 Statements (`segment.py`)

A statement is one of the following:
- a sentence of the prose view;
- a derivation line;
- a display row;
- a list item;
- a code block;
- a table.

Sentences come from the shared `sentence_boundaries` with three STEM-only boundary rules:

- after `<number> <unit>.` and after a masked span followed by `.`, a space and a capital;
- after a single lower-case letter that is a symbol in scope, followed by `.`, a space and a
  capital (`the speed is v. Then …`);
- neither rule applies to `c.` or `p.` followed by a digit (circa, page).

Part labels (`(a)`, `b)`, `(b)(ii)`, `Part (c)`, `Question 2`, Markdown headings) are recorded
as structure, not claims, and scope a part's checks. History's splitter and its
`ABBREVIATIONS` are untouched; the wrapper lives only in `stem/segment.py`.

### 4.4 Lexer (`lexer.py`): one forward pass, no backtracking regex

- **NUMBER.**
  - Digits with an optional decimal point.
  - A decimal comma only when 1 or 2 digits follow and no space follows outside a coordinate
    pair.
  - Thousands groups with `,` or a thin space, in groups of exactly three.
  - Scientific notation: `1.2 × 10⁶`, `1.2 x 10^6`, `1.2×10^{6}`, `1.2*10**6`, `1.2e6`,
    `6.0E-3`, with a Unicode minus allowed in mantissa and exponent.
  - Base-marked integers: `FF₁₆`, `0xFF`, `0b1010`, `1010₂`, `(255)₁₀`.
- **IDENT.**
  - A Latin letter, or a Greek letter (Unicode or `\alpha` and its kin).
  - Subscripts are part of the name (`v_0`, `v₀`, `v_{max}`), and so are primes.
  - A `Δ` or `\Delta` prefix fuses into one symbol.
- **FUNC.** `sin cos tan arcsin arccos arctan sin⁻¹ cos⁻¹ tan⁻¹ ln log lg exp sqrt √ ∛`, and
  `\sin \cos \tan \arcsin \arccos \arctan \ln \log \exp \sqrt`.
- **LaTeX allowlist.**
  - Structure: `\frac \dfrac \tfrac \sqrt \sqrt[2] \left \right`.
  - Operators: `\cdot \times \div \pm \mp`.
  - Spacing: `\, \; \! \quad`.
  - Text: `\text \mathrm \operatorname`.
  - Greek letters and `\pi`.
  - Relations: `\approx \neq \ne \leq \le \geq \ge \lt \gt \Rightarrow \implies \to \rightarrow
    \rightleftharpoons \therefore`.

  Any other command makes the span Unparsed (ST-PARSE-001), with the command named.
- **OP and REL** tokens, grouping `() [] {}`, COMMA, PERCENT, DEGREE `°`, primes `′ ″` (arc
  minutes and seconds or inches only directly after a number), ABS bars, `!`, ratio `:`
  between numbers, a magnification suffix `×` after a number at the end of an operand, and the
  Boolean words `AND OR NOT XOR` (CS only).

### 4.5 Grammar (`parser.py`): Pratt, lowest to highest precedence

```
chain     := expr ( relop expr ){1,12}
relop     := = | ≈ | ≃ | ~ | ≠ | < | > | ≤ | ≥ | <= | >= | ⇒ | ∴ | → | ⇌ | ⇔ | \approx | \neq | \leq | \geq | \Rightarrow
             (→ and ⇌ are reaction arrows only in chemistry mode between two species lists; ⇔ is Boolean equivalence only in CS)
expr      := term ( ( + | - | ± | ∓ ) term )*
term      := unary ( ( × | · | * | / | ÷ | \cdot | \times | \div | juxtaposition ) unary )*
unary     := ( - | + ) unary | power
power     := postfix [ ( ^ | ** | superscript ) exponent ]           right-associative
exponent  := signed integer literal (|n| ≤ 12) | ½ | 1/2              (½ is read as a square root)
postfix   := primary [ % | ° | ′ | ″ | × (magnification) ]
primary   := number | quantity | symbol | func_app | ( expr ) | { expr } | [ expr ] (concentration in chemistry)
           | \frac{expr}{expr} | \sqrt{expr} | √primary | √(expr) | | expr | | ratio
quantity  := number unit_expr          (the unit token must end the operand: next is an operator, a relation, a close or the end)
ratio     := number : number           (only directly beside a relation sign: a:b = c:d)
func_app  := FUNC ( (expr) | {expr} | primary )
```

Unsupported, each as a named `Unsupported(reason)` node:
- a fractional or symbolic power;
- `!`;
- `Σ`, `∫` and `lim`;
- `d/dx` and `dy/dx`;
- `f′(x)` and `f''(x)` (derivative);
- vectors in bold, arrows or `\vec`;
- matrices;
- `i` beside a number or `±` (complex number);
- asymptotic notation (`O(…)`).

### 4.6 Implicit multiplication and scope

- **Segmentation.** A letter run inside a math span is segmented by the longest prefix over
  the names in scope:
  - declared symbols;
  - formula left-hand sides;
  - the STEM name table (`KE PE GPE EMF pH pOH Ka Kb Kw Kc Kp Mr Ar N_A`);
  - function names.

  With scope `{u, v, a, t}`, `at` is `a·t`; `mgh` is `m·g·h`; `½mv²` is `½·m·v²`; `2πr` is
  `2·π·r`. A run that matches no name splits into single letters. If two segmentations both
  match the scope, both are kept as readings (at most 2); with more readings, ST-PARSE-002.
- **Numbers, units and symbols.**
  - A number followed by a space and a unit token is a Quantity when the unit token ends the
    operand.
  - A number directly followed by a declared symbol is multiplication.
  - A letter at the start of an expression is a symbol: in `m = 2.0 kg`, `m` is a symbol and
    `kg` a unit.
- **Bindings** (`scope.py`): `symbol → [(value, unit, half_width, source, claim_id)]`. Sources:
  - the request text (read by the same front end);
  - a `Given:` or `Data:` block;
  - `let`, `take` or `taking x = …`;
  - an earlier result of the answer;
  - a value the answer states for a constant.

  The front end never adds a constant value to scope; see D3 for the guarded booklet reading in
  checks. Rebinding adds a binding (ST-SCOPE-001 info when the value differs). A substituted
  value passes if it matches any binding of that symbol, so part (b) reusing part (a)'s letter
  is never flagged.
- **Formulas.** A left-hand symbol or `f(x)` maps to an expression, recorded from definition
  and law links.

### 4.7 Relations (`relations.py`)

A chain `L0 op1 E1 … opk Ek` may continue across lines. Each link is classified by its two
endpoints: *symbolic* (contains an unbound symbol), *numeric* (closed, possibly with units) or
*value* (a single number or quantity). The link's claim ids are the statements that hold its
two endpoints.

| Link | Example | Outcome |
| --- | --- | --- |
| symbolic = symbolic, first link with a lone left-hand side | `F = ma`, `a = \frac{v-u}{t}` | law or definition: recorded as a formula, not checked (its truth is out of scope) |
| symbolic → symbolic later, or across `⇒`, `∴`, "rearranging", "so", "gives", or a display row | `v² = u² + 2as ⇒ s = (v² − u²)/(2a)` | `stem-alg` |
| symbolic → numeric | `(v − u)/t = (20 − 0)/4.0` | `stem-sub` (substitution fidelity) |
| numeric → value, numeric → numeric | `(20 − 0)/4.0 = 6.0` | `stem-eq` |
| value → value, both with units | `72 km h⁻¹ = 20 m s⁻¹` | `stem-cnv` |
| `<`, `>`, `≤`, `≥`, `≠` between values or bound symbols | `T₁ = 300 K > T₂ = 250 K` | `stem-cmp` |
| prose value after `therefore`, `so`, `hence` or "the answer is", against the chain's final value | "The acceleration is therefore 6.0 m s⁻²." | `stem-res` |
| equation, then a stated root set | `x² − 5x + 6 = 0 ⇒ x = 2 or x = 3` | `stem-sol` |
| answer `Given:` binding against a request binding of the same symbol, or a request quantity of the same dimension | `Given: v = 20 m s⁻¹` | `stem-giv` |
| final value against a show-that target in the request | "Show that n ≈ 2.0 mol" | `stem-tgt` |
| chemical equation | `2H₂ + O₂ → 2H₂O` | `stem-chem` |
| Boolean equivalence | `¬(A ∧ B) = ¬A ∨ ¬B` | `stem-bool` |
| truth-table block | header `A B A∧B` | `stem-tt` |
| based numerals | `FF₁₆ = 255` | `stem-base` |
| a relation whose endpoints contain Unsupported | `f′(x) = 3x + 2` | ST-UNDEC-001 (reason) |
| a numeric relation whose operands include a symbol with no binding and no admissible booklet reading | `E = hf = 3.3e-19` with f unbound | ST-UNDEC-002 |

A bare value binding with no relation stated (`The speed is 15 m/s.`, `m = 2.0 kg`) is a
binding, not a check. That keeps the existing Physics fixtures free of new findings.

Check ids are planned here, deterministically, in document order: `stem-eq-1`, `stem-eq-2`,
… per kind. Parser and pack therefore agree on them. A planned check that `to_ir` cannot
encode keeps its id: the undecided finding names the id instead of a check being built.

### 4.8 Chemistry and Computer Science readings

- **Chemistry** (`chem.py`, chemistry, biology and ESS profiles):
  - Formulas with element symbols from the periodic-table symbol list (symbols only, no masses),
    counts (subscript or digit), parenthesised groups nested at most 3 deep, and hydrate dots
    (`CuSO₄·5H₂O`).
  - Charges `²⁺`, `⁻`, `^{2+}`; electrons `e⁻`.
  - State symbols `(s) (l) (g) (aq)` are ignored.
  - Arrows `→`, `⇌` and `\rightleftharpoons`; fractional coefficients `½O₂`.

  Isotope notation, structural diagrams and unknown element symbols give ST-CHEM-001.
- **Computer Science** (`boolean.py`):
  - Boolean expressions with `∧ ∨ ¬ ⊕`, `AND OR NOT XOR`, `·` and `+` in Boolean context, and
    overbar or prime negation.
  - Truth tables of at most 5 inputs (32 rows).
  - Based numerals.
  - Code is never read for meaning (ST-CODE-001 info).

### 4.9 Bounds (`StemLimits`)

| Bound | Value | When exceeded |
| --- | --- | --- |
| response characters | 400,000 (the report contract) | the contract rejects it first |
| math span characters | 2,000 | ST-LIM-001; the span stays a text claim |
| tokens per span | 400 | ST-LIM-001 |
| chain links | 12 | links after the 12th: ST-LIM-001 |
| AST nodes per expression | 256 | ST-LIM-001 |
| AST depth | 24 (checked before each descent; IR depth after encoding stays under 40) | ST-LIM-001 |
| integer power | \|n\| ≤ 12 | ST-UNDEC-001 |
| scientific exponent | \|e\| ≤ 99 | ST-LIM-001 |
| written digits per number | 30 | ST-LIM-001 |
| readings per expression / per check | 2 / 4 | ST-PARSE-002 |
| bindings per symbol | 8 | the oldest are dropped from matching; ST-SCOPE-001 info |
| symbols per check | 48 (the IR limit is 64) | ST-LIM-001 |
| interval operands per Form S check | 6 | ST-LIM-001 |
| STEM checks per report | 128 | ST-LIM-002 names the count and the first unchecked ids |
| statements (claims) | 512 (the report contract) | overflow merges into `s.tail` with the unresolved-issue text the bus turns into INT-REQ-013 |
| chemistry species per side; atoms per species | 16; 999 | ST-CHEM-001 |
| truth-table inputs | 5 | ST-UNDEC-001 |
| document cache | 64 entries | LRU eviction |
| enclosure arguments | trig after reduction modulo 2π; ln and log10 over (0, 10¹⁰⁰]; exp over \|x\| ≤ 700; ≤ 400 series terms | ST-UNDEC-001 |

---

## 5. Numbers, significant figures and tolerance

### 5.1 Exact numbers (`numbers.py`)

An `ExactNumber` holds:
- the exact `Fraction` value as written (scientific notation expanded exactly);
- the significant figures: leading zeros are not significant, trailing zeros after the point
  are, and scientific notation counts the mantissa;
- `last_place`, the power of ten of the last written digit;
- `half_width = ½·10^last_place`;
- `exact`: true for integers and fractions with no decimal point anywhere;
- the decimal exponent, for scaling.

A bare `0` is exact zero. `0.0` has a half-width of 0.05.

**Trailing zeros of an integer** (no decimal point): they are significant only up to the
smallest significant-figure count among the expression's measured operands, with at least 1.
So `= 1200` with 2-s.f. operands has h = 50. With no measured operands, `h = ½·10^k` for k
trailing zeros.

### 5.2 The STEM tolerance rule (`tolerance.py`; repeated in every check description)

Let E be the written expression, S the written value it is said to equal, and C the exact
value of E. Values are compared under the reading in force (section 6.4).

- **R1 Half-width h(S).** Half a unit in the last written digit of S's mantissa, times its
  power of ten: 5.0 gives 0.05; 1.20 × 10³ gives 5; 3/4 or a surd gives 0. Section 5.1 gives
  the integer trailing-zero rule.
- **R2 Relative slack τ.**
  - `=` with any decimal operand or decimal S: 1/100. This covers constants written to fewer
    digits than were used (9.8 against 9.81 is 0.1 %; 3.00 × 10⁸ against 2.998 × 10⁸ is
    0.07 %). It stays well below the error classes this design must catch (a wrong formula,
    substitution, digit or power of ten, typically 5 % or more).
  - `≈`, `≃` or `~`, or `=` after "approximately", "about", "roughly" or "estimate": 1/20.
  - **Exact mode** (every operand and S exact): τ = 0 and h = 0. So `7/3 = 2` fails, while
    `√2 = 1.41` (S is a decimal) passes under R1.
- **R3 Interval readings.** These operands may take any value in an interval:
  - a carried intermediate: an operand whose written value is the answer's own earlier result
    (traced by symbol, or by an equal numeral with the same unit), or one marked approximate,
    ranges over `[w − h(w), w + h(w)]`;
  - a written constant: a literal matching a table constant at its written precision ranges
    over the hull of `[w − h(w), w + h(w)]` and the booklet value (D3a);
  - an unbound standard-constant symbol with an admissible booklet reading ranges over the
    hull of its accepted values, for example g in [9.80, 9.81] (D3b, warning on failure);
  - an enclosure symbol (π, e or a function value) ranges over its enclosure (D4).

  Given data, constants whose value the answer states, and exact coefficients are taken as
  written.
- **R4 Band.** The check passes iff there are operand values under R3 with `|C − S| ≤ h(S) +
  τ·|C|`. The band is symmetric around the computed value and sign-aware, because `|·|` is
  encoded with `ite`. Negative values and zero need no special case beyond R1's exact zero.
  - **Form E** (no interval operand): an entailment. Symbols `c` and `r`; premises
    `C_DEF: c = ⟦E⟧` and `R: r = S`, plus auxiliaries and guards; conclusion `STATED: |c − r| ≤ h
    + τ·|c|`; expected ENTAILED. A COUNTEREXAMPLE's model shows `c` beside `r`. The core contains
    `C_DEF` and `R`, so E108 (vacuous) cannot arise.
  - **Form S** (one or more interval operands): a satisfiability query. Interval premises
    `X_LO` and `X_HI`, the definitions, and `BAND` as a premise; expected SATISFIABLE.
    UNSATISFIABLE means no admissible reading of the rounded values gives the stated value, and
    the core names the intervals and the band. The description says exactly that, so
    SATISFIABLE is never read as "true". Builder invariant: every symbol is pinned,
    interval-bounded, or an auxiliary defined by a premise, so a free symbol can never make
    Form S vacuously satisfiable.
- **R5 Conversions.** `2.5 km = 2500 m`, `72 km h⁻¹ = 20 m s⁻¹` and `25 °C = 298 K` use τ = 0.
  The factors are exact, so the only slack is h(S).
- **R6 Comparisons** (`<`, `≤`, `>`, `≥`, `≠`) between written values are exact, with no slack,
  as in quant's series checks.
- **R7 Substitution fidelity.** A substituted numeral w matches a binding b iff `|w − b| ≤ h(b) +
  h(w)`, in b's written unit or in SI. The two readings are a disjunction, so 2500 and 2.5
  both match 2.5 km. τ = 0.
- **R8 Restated result.** A prose value S′ matches the chain's final value S iff `|S − S′| ≤
  h(S) + h(S′)`, in SI, with τ = 0.
- **R9 Prose relations** (per cent, fold, share and total) keep quant's `TOLERANCE_RULE`: 5 %
  and the 0.5-point floor. In SI reading the band is made sign-aware (section 12). Those
  statements are approximate by nature; equations are precise statements.
- **R10 Roots.** A stated decimal root r of a polynomial equation passes iff a real root lies
  in `[r − h(r), r + h(r)]` (Form S). An exact root passes iff it satisfies the equation exactly
  (linear substitution, D1).

**The observed case.** C = 5, S = 6.0, h = 0.05, τ = 1/100, and |5 − 6| = 1 > 0.05 + 0.05, so
the check fails. Under quant's 5 % rule it would have passed anything from 4.76 to 5.26.

**Short form** (the `[rule]` suffix of every description, 300 characters or fewer): "STEM
tolerance: S must lie within h + τ·|C| of the value C computed from the written expression;
h is half a unit in S's last written digit; τ is 1 % for '=', 5 % for '≈'/about, 0 for
conversions, comparisons and exact work; rounded intermediates, constants and function values
range over their rounding or enclosure intervals."

---

## 6. Units and dimensions (`units.py`)

### 6.1 Table

- **Dimensions.** A 7-tuple of ints over (m, kg, s, A, K, mol, cd), plus an angle flag.
- **Base units.** m, g (kg is the base), s, A, K, mol, cd.
- **Derived units.** N, J, W, Pa, Hz, C, V, Ω and ohm, F, H, T, Wb, S, Bq, Gy, Sv, lm, lx, rad, sr.
- **Accepted units.**
  - Time: min, h, d.
  - Volume: L and l, dm³, cm³.
  - t (tonne): ESS and Design Technology only.
  - Energy and mass: eV, u and Da.
  - Length: Å, AU, ly, pc.
  - Pressure: bar, atm, mmHg.
  - Angle: °, ′, ″.
  - Ratio: %, ppm.
- **Affine units.** °C and °F.
- **Spelled-out units.** metre and meter, seconds, newtons, "metres per second squared",
  "per cent", and so on.
- **Prefixes.** Q R Y Z E P T G M k h da d c m µ/μ/u n p f a z y r q, applied by longest
  match, and only to units that take a prefix. SI binding applies: `ms` is a millisecond, `m s`
  is metre second, and `Nm` and `N m` are newton metre.
- **Unit expressions.** Space, `·`, `*`, `/`, and exponents `⁻²`, `^-2`, `^{-2}`, `**-2`. For
  example `m s⁻²`, `m/s/s`, `J mol⁻¹ K⁻¹`, `mol dm⁻³`, `kg·m/s`, `kJ mol⁻¹`.
- **Factors.** SI conversion factors are exact `Fraction`s. The affine offset (273.15) is
  applied only in explicit °C/K conversion checks. It is never applied to a Δ-prefixed symbol,
  or to a quantity the sentence calls a change, difference, rise or fall.

### 6.2 Where a unit is read

A unit is read only after a number, after a closing group that contains a number, or inside
`\text{}` or `\mathrm{}`. Elsewhere a letter is a symbol.

### 6.3 Ambiguity table (one reading per profile; an ambiguity that matters to a check becomes two readings)

| Token | After a number | Elsewhere |
| --- | --- | --- |
| g | gram | symbol (gravity) |
| M | molar in chemistry and biology; molar or mega in physics (two readings, ST-UNIT-002 info) | symbol |
| h | hour | symbol (height, Planck) |
| t | tonne in ESS and Design Technology only | symbol |
| A | ampere (never the article inside math) | symbol |
| K / k | kelvin / kilo- only as a prefix | symbol |
| T, F, L / l | tesla, farad, litre | symbol |

### 6.4 Readings: as written or SI

- Every quantity in the link carries a unit, or is a symbol bound with a unit: compare **in
  SI only**. So `2.0 km / 4.0 s = 0.5 m s⁻¹` fails, as it should.
- Some operands are bare numbers and some carry units: **disjunction {as written, SI}**. So
  `v = 72 km h⁻¹ ÷ 3.6 = 20 m s⁻¹` (3.6 is a bare factor) and `4.5/6.0 × 100 = 75 %` both pass.
- No operand carries a unit: compare as written, and S is read both as its number and in SI
  (`20 × 25 = 0.5 km` passes in SI).
- An unknown unit word: ST-UNIT-001 warning. The relation is checked as written only, with
  `failure_severity="warning"`.

### 6.5 Dimension checks (deterministic integer-vector arithmetic; warnings only)

- **ST-DIM-001.** The two sides of a stated relation have different dimensions, where every
  operand's unit is read unambiguously or is a bound symbol's unit. Example: `a = (v − u)/t =
  5.0 m s⁻¹` with v in m s⁻¹ and t in s.
- **ST-DIM-002.** A sum or difference of terms with different dimensions.
- Bare numbers are "unitless as written", not dimensionless, so they never trigger a
  dimension finding.
- Dimension findings are warnings because unit reading is the least certain part of the
  front end. The arithmetic check of the same link is still built and decided by the engine.

---

## 7. IR translation (`to_ir.py`): IR 1.0, no schema change

### 7.1 Sorts and literals

- **Sorts.** Real for physical and mathematical values. Int for stoichiometric counts, based
  numerals and truth-table rows. Bool for CS logic.
- **Literals.** Exact: an `a/b` text, an integer, or a decimal (`RealConst` accepts all three).
  Scientific notation is expanded exactly, after factoring (7.3).

### 7.2 Symbols

- Names map one-to-one into `^[a-z][a-z0-9_]{0,63}$`: v → `s_v`, V → `s_cap_v`, v₀ →
  `s_v_0`, Δv → `s_delta_v`, θ → `s_theta`, f′ → `s_f_prime`, with a numeric suffix on
  collision.
- `Symbol.meaning` carries the original token, its unit and the binding source.
- Auxiliaries are `q_<n>` (quotient), `p_<n>` (power base), `sq_<n>` (root), `enc_<n>`
  (enclosure) and `k_<n>` (reading).

### 7.3 Decimal-exponent factoring (`scaling.py`)

Each subtree is normalised to `(mantissa AST, integer exponent K)`:
- products and quotients add and subtract exponents;
- integer powers multiply them;
- sums align to the smallest exponent of their terms, scaling the other mantissas by exact
  powers of ten.

The stated value is scaled by the same exact factor, `S′ = S·10^−K`, `h′ = h·10^−K`. Then
`|C − S| ≤ h + τ·|C| ⇔ |M − S′| ≤ h′ + τ·|M|`, because 10^K > 0. So `h c / λ` with h =
6.62607015 × 10⁻³⁴ is decided with small literals. `notes` records "decimal exponent factored:
10^K". ST-LIM-001 is reported only when a literal still has more than 40 digits after
factoring.

### 7.4 Node encodings

| Construct | Encoding | Policy |
| --- | --- | --- |
| Quantity | literal × exact SI factor, folded into the mantissa and exponent | linear |
| `+ − unary−` | `add` (n-ary, flattened up to 32 arguments, nested beyond), `sub`, `neg` | linear |
| `× · *` and juxtaposition | `mul` | linear if at most one factor is not closed |
| `a / b`, b a single literal | `div` (validator policy satisfied) | linear |
| `a / b`, b closed but compound | auxiliary q: `Q_DEF q·b = a`, `GUARD b ≠ 0`. Precheck: b exactly 0 gives ST-UNDEF-001 and no check | linear |
| `a / b`, b contains symbols | `Q_DEF q·b = a`, `GUARD b ≠ 0` (grounded `assumption`). Never a `div` by a variable (E202) | nonlinear |
| `xⁿ`, 2 ≤ n ≤ 12 | `mul` of n copies; a compound base first gets `p = x` | linear if x is closed |
| `x¹`, `x⁰` | x; `1` with `GUARD x ≠ 0` (0⁰ gives ST-UNDEF-001) | — |
| `xⁿ`, n < 0 | `q·x^|n| = 1`, `GUARD x ≠ 0` | linear if x is closed |
| `√x`, `x^½` | `sq ≥ 0`, `sq·sq = x`. Precheck: a closed negative x gives ST-UNDEF-001 | nonlinear |
| `\|x\|` | `ite(x ≥ 0, x, −x)` | linear |
| `n %` | n/100 (SI reading); n (as written) | linear |
| `±` inside a formula | `or` of both sign choices | — |
| `value ± uncertainty` | an interval binding | — |
| ratio `a:b = c:d` | `a·d = b·c` over closed terms | linear |
| exact-table function | the exact value (rational, or a surd through `sq` of 2 or 3) | as the surd |
| other sin, cos, tan, arcsin, arccos, arctan, ln, log10, exp of a closed argument; π; e | enclosure symbol `enc` with `ENC_LO ≤ enc ≤ ENC_HI` (grounded `arithmetic_fact`, note "enclosure computed by the STEM pack; the engine decides the stated relation over every admissible value"); forces Form S | linear |
| a function of a non-closed argument | ST-UNDEC-001 ("function of an unknown") | — |
| Boolean `∧ · AND`, `∨ + OR`, `¬ ′ overbar NOT`, `⊕ XOR` | `and`, `or`, `not`, `not(iff)` | — |
| based numeral | `IntConst` of its value | — |

### 7.5 Enclosures (`enclosures.py`)

- **Method.** Argument reduction, then a Taylor series in exact `Fraction`, with an explicit
  remainder bound. The result is `[lo, hi]` with `hi − lo ≤ 10⁻¹⁵·max(1, |mid|)`.
- **Cross-check.** The routine checks `lo ≤ float_libm(x) ≤ hi`, within 10⁻⁹ relative,
  using the standard `math` module. A mismatch gives ST-INTERNAL-001 and no check.
- **Bounds.** Iterations and argument ranges are bounded (section 4.9).
- **Degrees.** An angle is in degrees when written with ° or when the profile and context say
  so. Otherwise it is in radians, and an ambiguous angle unit gives two readings.

### 7.6 Grounding of premises (provenance the engine reports, never judges)

| Premise | Grounding |
| --- | --- |
| a value located in the request text | `task_setting`, `verified=True` (located deterministically) |
| the report's own figures, `C_DEF`, `R` | `supplied_text`, `verified=True`, note "figure stated in the report itself" (quant's convention) |
| a stated law, or the preceding relation used as an algebra premise | `specialist_inference` |
| guards and step side conditions | `assumption` |
| auxiliary definitions (`Q_DEF`, `S_SQ`, `P_DEF`) and enclosures | `arithmetic_fact`, note "encoding device: defines the auxiliary as the written expression; not a claim of the report" |
| a booklet value for an unstated symbol (D3b) | `assumption`, note "data-booklet value supplied by the STEM pack; the report did not state it" |

The engine then lists laws, guards, side conditions and supplied constants in
`ungrounded_dependencies`. A passing check therefore never hides what it relied on.

### 7.7 Problem fields

- `problem_id`: `stem-<kind>-<report>-<n>`, at most 128 characters; a long report id is cut and
  given a sha256 suffix.
- `claim_id`: `<report_id>:<first claim id>`, truncated the same way.
- `query`: `entailment` (Form E), or `satisfiability` (Form S, Boolean identities, truth
  tables).
- `notes`: the scope sentence; "policy: nonlinear" when used; the decimal exponent factored;
  the readings in force.

`notes` is part of the problem digest, so the binding covers them.

### 7.8 What is never encoded

- Truth of a law or a datum.
- Unit correctness beyond section 6.5 and the explicit conversion checks.
- Calculus: derivatives, integrals, limits, series.
- Σ with symbolic bounds.
- Vectors, matrices and complex numbers.
- Factorials and combinatorics with `!`.
- Fractional or symbolic powers.
- A function of an unknown.
- Probability distributions.
- Asymptotic notation.
- Code behaviour.
- Diagram or graph readings.
- Molar masses from formulas (that would be our data; it goes to the evidence service).

Each of these, when stated as a relation, is ST-UNDEC-001 with its reason.

---

## 8. Checks, finding codes and severities

### 8.1 Engine checks (`stem.checks.PlannedCheck`, converted to `FormalCheck` by `StemPack`)

New `FormalCheck` fields, all with defaults that keep every existing pack unchanged:
- `claim_ids: tuple[str, ...] = ()`;
- `policy: str = "linear"`;
- `failure_severity: Literal["error", "warning"] = "error"`;
- `inconsistent_is_failure: bool = True`.

Every STEM check sets `inconsistent_is_failure=False` (D13).

| Id (kind) | What is decided | Form, expected | Policy | Failure severity |
| --- | --- | --- | --- | --- |
| `stem-eq-N` (`stem_arithmetic`) | a numeric link `E = S` (and `≈`) | E: ENTAILED; S: SATISFIABLE | linear unless surds or two interval operands are multiplied | error; warning when a D3b booklet value was used or a unit was unknown |
| `stem-sub-N` (`stem_substitution`) | substituted numerals against the symbols' bindings (R7). When the symbolic and numeric sides have the same tree shape, each aligned symbol is checked; otherwise, if every symbol is bound, the symbolic side under its bindings is checked against the numeric side (Form S over the binding intervals). Never built when any symbol is unbound | E or S | as needed | error |
| `stem-alg-N` (`stem_algebra`) | the next relation follows from the preceding one, plus scope bindings of the symbols involved, plus at most 8 recorded formulas mentioning them, plus side conditions: divisors ≠ 0; a principal (non-negative) root in sciences profiles | E: ENTAILED | nonlinear when needed | error when the step is a pure manipulation (its symbols are a subset of the premise's symbols, bound symbols and included formulas); warning when it brings in unrelated symbols (an unstated law may be at work) |
| `stem-sol-N` (`stem_solution`) | membership: each stated root satisfies the equation (exact: linear substitution; decimal: R10). Completeness: the equation entails the disjunction of the stated roots, built only when the statement claims the full set and neither the statement nor the request restricts the domain ("positive", "x > 0", "length", "time", "reject") | E / S | membership linear; completeness nonlinear | error |
| `stem-cnv-N` (`stem_conversion`) | an explicit unit conversion (R5) | E | linear | error |
| `stem-cmp-N` (`stem_comparison`) | a stated order or inequality between values (R6); also linear inequality-solving steps | E | linear | error |
| `stem-res-N` (`stem_result`) | a prose restatement against the chain's final value (R8) | E | linear | error |
| `stem-giv-N` (`stem_given`) | an answer's `Given:` value against the request's binding of that symbol, or a request quantity of the same dimension | E | linear | warning (symbol identity across texts is a reading) |
| `stem-tgt-N` (`stem_target`) | the final value of a show-that answer against the request's target | E | linear | warning |
| `stem-chem-N` (`stem_balance`) | element and charge balance. Coefficients are pinned; tally symbols `t_<el>_l` and `t_<el>_r` are defined per element; the conclusion is a conjunction of equalities, so the counterexample model shows the unbalanced tallies | E (Int, or Real for fractional coefficients) | linear | error |
| `stem-bool-N` (`stem_boolean`) | Boolean identity: premise `NEG: ¬(lhs ⇔ rhs)` | satisfiability, expected UNSATISFIABLE; SATISFIABLE is a failure whose witness is a distinguishing assignment | linear | error |
| `stem-tt-N` (`stem_truth_table`) | every row's stated output: stated outputs are pinned Bool symbols; the conclusion is the conjunction over rows of `o_r ⇔ expr(row inputs)` | E | linear | error |
| `stem-base-N` (`stem_base`) | a base conversion as exact Int arithmetic | E | linear | error |

Each description has the form `<what was checked>: '<statement, ≤ 160 chars>' [claims s2.3,
s2.4] [<short rule>]`, at most 1,200 characters. Descriptions name readings, factored exponents,
supplied constants and side conditions.

### 8.2 Finding codes

The column "Decided by" means:
- **engine**: a signed Z3 result;
- **deterministic**: rule-based reading;
- **numeric**: exact `Fraction` precheck or bookkeeping.

The STEM pack itself emits **no error-severity structural finding**. Every STEM error comes
from an engine result.

| Code | Severity | Decided by | Meaning |
| --- | --- | --- | --- |
| INT-SUBJ-001 | error | engine | a check of the report's own STEM statement does not hold, and it rested only on what the report or request states plus exact encoding devices (existing code; now carries `claim_ids`) |
| INT-SUBJ-002 | warning | engine | such a check is undecided: UNKNOWN, TIMEOUT, UNSUPPORTED, INVALID_FORMALIZATION, INTERNAL_ERROR, a vacuous result (E108), or INCONSISTENT_PREMISES on a check with `inconsistent_is_failure=False` (existing code; now carries `claim_ids`) |
| INT-SUBJ-003 | error | deterministic | an error-severity pack finding, escalated (existing; STEM never produces one) |
| INT-SUBJ-004 | warning | engine | NEW: a check that relied on a reading the report did not state does not hold: a booklet value for an unstated symbol, symbol identity across request and answer, a show-that target, a step bringing in unrelated symbols, or an unknown unit |
| BR-INTERNAL-001 | warning | deterministic | NEW (`SubjectBranch.run_packs`): pack `<name>` failed internally (`<type>`) during `<checks or formal checks>`; its findings are missing from this receipt, and the router must not treat the pack as passed |
| ST-PARSE-001 | warning | deterministic | a math span uses notation outside the grammar (named: unknown LaTeX command, unbalanced group, fractional or symbolic power); its relations are not checked |
| ST-PARSE-002 | warning | deterministic | an expression has more than 2 readings (or a check more than 4): implicit multiplication or unit/symbol ambiguity; not checked |
| ST-UNDEC-001 | warning | deterministic | a recognised relation outside the encodings (calculus, limits, Σ, vectors, matrices, complex numbers, `!`, asymptotic notation, a function of an unknown, an approximation step such as sin θ ≈ θ, an angle range); the reason is named |
| ST-UNDEC-002 | warning | deterministic | a numeric relation depends on a symbol with no stated value and no admissible booklet reading |
| ST-UNDEF-001 | warning | numeric | a written expression is undefined (division by an exact zero, an even root of a negative value, the logarithm of a non-positive value, 0⁰); no check is built |
| ST-UNIT-001 | warning | deterministic | a unit expression is not recognised; the relation is checked as written only, at warning severity |
| ST-UNIT-002 | info | deterministic | an ambiguous unit symbol (M: molar or mega) is checked under both readings |
| ST-DIM-001 | warning | deterministic | the two sides of a stated relation have different dimensions (units read unambiguously) |
| ST-DIM-002 | warning | deterministic | a sum or difference of terms with different dimensions |
| ST-ALG-001 | warning | deterministic | a mathematics step takes only the non-negative square root, and no domain restriction is stated (the algebra is still checked under that side condition) |
| ST-CHEM-001 | warning | deterministic | a chemical equation cannot be read (unknown element symbol, isotope notation, a bound exceeded); its balance is not checked |
| ST-CODE-001 | info | deterministic | a code block is present; it was not executed and not checked |
| ST-SCOPE-001 | info | deterministic | a symbol is rebound to a different value inside the answer; substitutions match any binding |
| ST-LIM-001 | warning | numeric | an expression or literal exceeds a front-end or IR bound (span, links, nodes, depth, exponent, digits after factoring, symbols, intervals); not checked |
| ST-LIM-002 | warning | deterministic | more relations than the per-report check cap (128); the count and the first unchecked ids are named |
| ST-INTERNAL-001 | warning | deterministic | the STEM pack failed internally while building checks (or an enclosure cross-check failed); its checks are missing |
| CORE-QNT-001 | warning | deterministic | existing; in SI reading, new reasons: different dimensions, "a relative change on an offset temperature scale is not defined" |

Severity semantics are unchanged:
- an engine check that does not hold: INT-SUBJ-001 (error) or INT-SUBJ-004 (warning);
- undecided: INT-SUBJ-002 (warning);
- ST warnings make the status ACCEPTED_WITH_FINDINGS;
- info changes nothing.

All of these are content findings: the report is delivered, never REJECTED.

---

## 9. Claim extraction, roles and eligibility

### 9.1 `StemTextParser` (`adapters/stem_specialist/parser.py`, implements `ReportParser`)

- **Claims.** Claims come from `StemDocument` statements. Ids are `s<paragraph>.<statement>`:
  stable and deterministic.
- **Overflow.** Claims beyond 512 merge into `s.tail` with the unresolved-issue text the bus
  turns into INT-REQ-013, as in the generic parser.
- **Empty text** still raises `AdapterError` (`tests/channel/test_channel_robustness.py:57`).
  A code-only answer yields claims; it does not raise.
- **Markup.** `markdown.strip_markup` is not applied wholesale, because it drops code fences
  and some bracket lines. Headings become part labels. Emphasis is dropped only in the prose
  view. Code blocks, tables and data lines are kept.
- **Notes.** Notes and self-certification use the shared `is_note_sentence` and
  `is_self_certification` (role `other`).
- **Assumptions.** A claim whose numeric relations the pack decides carries the assumption
  "numeric relations of this statement are decided by the STEM pack checks <ids>". The ids
  are planned in the shared document.
- **Structured reports.** For a report that arrives structured (JSON), `StemPack` maps
  statements to the report's own claims by offset when the claim texts are offset substrings,
  else by the shared two-way substring rule (`_claims_mentioning`).

### 9.2 Roles (no new `ClaimRole`; D11)

| Statement | claim_role | proposed kind | materiality | Eligibility (existing rules) |
| --- | --- | --- | --- | --- |
| Given or data line; a binding whose value is in the request | evidence | arithmetic | supporting | QUANTITATIVE_CLAIM |
| Law or formula with no numerals (`F = ma`, "Using v² = u² + 2as") | evidence | factual | supporting | NOT_ELIGIBLE_FACTUAL, route `evidence_service` |
| Substitution or arithmetic step; symbolic algebra step | quantitative | arithmetic | supporting | QUANTITATIVE_CLAIM / ARITHMETIC_CONSTRAINT (rule 4 extended, 9.3) |
| Result: the last chain-bearing statement of a part, or a prose value after therefore/so/hence/"the answer is" | quantitative | arithmetic | material | QUANTITATIVE_CLAIM |
| Explanation paragraph: first substantive sentence | point | unknown | material | PROPOSITIONAL_ARGUMENT when supporting claims exist |
| Explanation sentence with because/since/so/therefore/hence/thus and no value | link (supports earlier claims of the paragraph) | unknown | supporting | PROPOSITIONAL_ARGUMENT |
| Other explanation | analysis | unknown | supporting | NOT_ELIGIBLE_INTERPRETIVE |
| Assumption ("neglecting air resistance"), also copied to `report.assumptions` | analysis | unknown | supporting | NOT_ELIGIBLE_INTERPRETIVE |
| Assumption that binds a value ("taking g = 9.81 m s⁻²") | evidence | arithmetic | supporting | QUANTITATIVE_CLAIM |
| Code block (text truncated by `truncate_claim_text`; ST-CODE-001 names it) | point | unknown | material when it answers the item | not eligible (no supports) |
| Table, data or vector line | evidence | arithmetic | supporting | QUANTITATIVE_CLAIM when it carries figures |
| Notes, self-certification | other | — | supporting | never material |

Every chain-bearing part yields a material result, so INT-REQ-012 ("no answer") never fires
on a derivation.

### 9.3 Eligibility (`translate/eligibility.py`)

Rule 4 (COUNT_ROLES) also accepts a text with a mathematical relation sign between operands
(`=`, `≠`, `<`, `>`, `≤`, `≥`, `≈`). This applies only when the profile allows
QUANTITATIVE_CLAIM, so argument-only profiles are unchanged. `has_numeral` also counts
superscript and subscript digits. POLICY_VERSION is bumped. Eligibility classes for the
sciences, mathematics and CS profiles remain `_QUANTITATIVE`.

---

## 10. Routing and profiles

### 10.1 `translate/subjects.py`

1. **Word-boundary aliases.** Alias matching uses word boundaries on the normalised label,
   `(?<![a-z0-9])alias(?![a-z0-9])`, keeping the longest match. This fixes:
   - "Assessment", "Process" and "Stress and Wellness" resolving to `ess`;
   - "Free fall" and "Software engineering" resolving to `extended_essay`.

   Every display name and "display name + HL" must still resolve to its own profile, and
   "Underwater Basket Weaving" must stay UNKNOWN (`tests/translate/test_overseer_round1.py`).
2. **STEM aliases.**
   - phys → physics; chem → chemistry; bio → biology.
   - cs, comp sci, computer sci, software engineering → computer_science.
   - environmental science, environmental systems → ess.
   - statistics, stats → mathematics_ai.
   - maths: aa, math: aa, mathematics: aa, aa hl, aa sl → mathematics_aa, and the AI
     equivalents → mathematics_ai.
   - further mathematics → mathematics_aa (working configuration, recorded as such).
3. **A new profile `stem`** (group sciences, `_QUANTITATIVE`, Int and Real). It covers
   "science", "sciences", "general science", "stem" and "engineering". It also covers labels
   that name two or more different sciences ("Physics/Chemistry"): when matches fall in more
   than one sciences profile, resolve to `stem` rather than the longest.
4. **`can_check` and `cannot_check`** for the sciences, mathematics and CS profiles are
   rewritten to the truth.
   - Deterministic STEM checks decide the written arithmetic, substitutions, conversions,
     dimensions (warnings), balances, algebraic steps and Boolean identities.
   - The model translator's formalisations do not check units.
   - Nothing establishes physical validity, the truth of laws or data, diagram or graph
     reading, or calculus.
5. **STEM encoding guidance** in `prompt_profile_text` for the STEM profiles, used by the
   model translator path:
   - exact numerals with no exponents;
   - substitute given values;
   - one symbol per quantity, namespaced per claim (`s<claim>_v`) to avoid cross-claim unification;
   - units as assumptions;
   - `sqrt` and trig as squared comparisons or UNSUPPORTED.

   This bumps TRANSLATOR_VERSION. The pinned prompt version `translate_v1` and its file are
   unchanged.

### 10.2 `branches/registry.py`

`CORE_SI = CorePack(reading=SI_READING)`. Its `name` is still `"core"` and it comes first in
every STEM branch (`tests/branches/test_quant_and_packs.py:77-79`).

| Branch key | Profile keys | Parser | Packs |
| --- | --- | --- | --- |
| `sciences` | physics, chemistry, biology, ess, sports_science, design_technology, stem | `StemTextParser(agent_id="science-specialist")` | (CORE_SI, StemPack("sciences")) |
| `mathematics` | mathematics_aa, mathematics_ai, mathematics | `StemTextParser(agent_id="maths-specialist")` | (CORE_SI, StemPack("mathematics")) |
| `computer_science` | computer_science | `StemTextParser(agent_id="cs-specialist")` | (CORE_SI, StemPack("computer_science")) |

`generic` stays the default for `unknown`. `StemPack` sub-features follow
`resolve_profile(report.subject)`: chemical equations for chemistry, biology and ESS; the
molar `M` preference for chemistry and biology. Each STEM branch sets
`hub_hooks=STEM_HOOKS` (section 11).

**Recorded behaviour change.** Two existing assertions encode today's routing:
- `tests/branches/test_hub.py:46`: `branch_for("Chemistry") == "generic"`;
- `tests/branches/test_quant_and_packs.py:76`: `for_subject("Physics")[0].key == "generic"`.

The user's goal and the observed defect are exactly this routing, so it must change. Stage
`branch` replaces each with an assertion of equal strength for the new branch (`"sciences"`)
and keeps the unknown → generic assertion beside it. Nothing is deleted. The stage report
lists the change for the overseer audit and the user's sign-off. Every other existing test
that runs a Physics plan must pass unchanged. In particular `StemPack` emits nothing on `The
speed is 15 m/s.` (no relation is stated) and only info for unchecked code.

---

## 11. Hub, channel and receipts

### 11.1 `branches/base.py`

- `FormalCheck` gains the four fields of section 8.1.
- `SubjectBranch` gains `hub_hooks: Optional[BranchHooks] = None`.
- `SubjectBranch.run_packs` guards each pack call. On an exception it adds BR-INTERNAL-001
  and continues with the next pack.
- It prefers `pack.formal_checks_for(report, request_text)` when the pack defines it.
- On relay (`req=None`) STEM checks bind only to the answer's own givens, and `stem-giv` and
  `stem-tgt` are not built.

### 11.2 `channel/bus.py`

`_branch_checks`:
- calls `verify(fc.problem, cfg, limits=policy_limits(fc.policy), signing_key, key_id)`,
  where `cfg` is the channel config. For the `nonlinear` policy it uses the config with
  `rlimit=NONLINEAR_RLIMIT`, so cutoffs are deterministic. An unknown policy name gives
  INT-SUBJ-002 "unknown policy"; it is never run under some other policy.
- maps the status as follows:
  - `satisfied = True` iff the status equals `expected_if_sound` and no E108 diagnostic is
    present;
  - `satisfied = False` iff the status is definitive and not the expected one, except
    INCONSISTENT_PREMISES when `inconsistent_is_failure` is False;
  - `None` otherwise.

  Today's False list misses SATISFIABLE for checks expecting UNSATISFIABLE, and an ENTAILED
  result carrying E108 shows as satisfied today. Existing ENTAILED-expecting checks with
  non-vacuous proofs keep their behaviour.
- maps `False` with `failure_severity="error"` to INT-SUBJ-001, `False` with `"warning"` to
  INT-SUBJ-004, and `None` to INT-SUBJ-002. Each carries `claim_ids=list(fc.claim_ids)`.
- truncates `ConstraintResult.detail` and finding messages with `translate.common.truncate`
  (2000 each), so a long description can never raise out of `hub.receive`. Each verify call
  and result construction is guarded: an exception becomes INT-SUBJ-002 "internal" for that
  check alone.
- **Degrades safely.** If the policy pass-through were missing, nonlinear checks would come
  back UNSUPPORTED (E201) and show as undecided, never as success.

Hooks (`stem/hub_hooks.py`; none for other branches, so their behaviour is unchanged):
- `coverage_terms(claim)`, read by `_coverage`: quantity names keyed by the dimensions of the
  claim's quantities (m s⁻² → acceleration; N → force, weight, tension; J → energy, work; …)
  and by symbol names bound in a `Given` block. An equation-only correct answer then does not
  get a heuristic INT-REQ-004 warning. The method stays `lexical_heuristic`.
- `echo_exempt(report, request_text)`, read by `_request_echo`: a STEM answer containing at
  least one planned computation link (`stem-eq`, `stem-alg` or `stem-sol`) that is absent from
  the request is never INT-REQ-011. This fixes the false error on the correct show-that answer
  `n = m/M = 36 g / 18 g mol⁻¹ = 2.0 mol`.
- `request_imperatives`, passed to `extract_items(text, extra_imperatives=…)`: determine,
  deduce, derive, state, find, solve, sketch, estimate, predict, verify, show. Multi-part STEM
  questions then become one item per part.
- `word_count_view(text)`, read by `count_answer_words`: LaTeX control words are not words,
  and each math span counts as one word. This avoids a false INT-REQ-005.

### 11.3 `channel/request_parser.py`

`extract_items(text, *, extra_imperatives=())` and `count_answer_words(text, *, view=None)`.
The defaults reproduce today.

### 11.4 Receipts

Receipts are unchanged in shape:
- `formal_checks` holds `ConstraintResult(constraint_id=check_id, method="formal",
  formal_result_id, formal_status)`;
- `structural_findings` holds the ST findings;
- the summary keeps counts "N (ok, FAILED, undecided)", names at most 8 FAILED and 8
  undecided ids, shows the code histogram (ST-* included), and ends with `_SCOPE_TAIL`.

Check ids are short and stable, as in section 8.1.

### 11.5 `integrity/ledger.py`

Synthesis-fidelity figure extraction (INT-LEDGER-0xx) reads scientific notation (`3.0e8`,
`6.67 × 10⁻¹¹`) through `stem.numbers`. Today `3.0e8` yields no figure and `6.67 × 10⁻¹¹`
yields 6.67 and 10. Figures with no exponent are read as today.

---

## 12. CorePack and quant in SI reading

`quant.py` gains a keyword-only `reading: QuantReading` parameter. It is a frozen, hashable
dataclass and is part of the `_analyse` cache key. It carries the scale vocabulary, a
figure-unit reader, the sentence and clause splitters, the band builder and a view function.
`GENERAL` reproduces today's module constants exactly, and every existing quant test runs on
it. `SI_READING` (`stem/si_reading.py`) changes the following:

- **Scale words.** Only spelled-out words (thousand, million, billion, trillion, bn) are
  scales. m, k, K, A and g are never scales, so `500 mm to 2 m` and `300 K` are read correctly.
- **Units.** A figure followed by a unit symbol is read through `stem.units` into an SI value
  and a dimension.
  - Pairs are comparable when their dimensions are equal: `500 g to 1.0 kg` is a doubling,
    `2 kg to 500 g` is a fall of 75 per cent, and `3.0 A to 1.5 A` pairs.
  - Different dimensions are undecided, with the reason named.
  - A relative change on an affine scale is undecided.
- **Numbers.** Scientific notation, `−` and `-` are read, and a U+2212 sign on a stated change
  is honoured. Repeated folds are read: "halved twice" is ×¼; "doubled three times" is ×8.
- **Band.** The band is sign-aware, `|C − S| ≤ tol·|C| + floor`. `S = 0` is decided explicitly.
- **View.** quant reads the math-masked view, so relation-bearing math spans are
  placeholders. quant sees only prose relations and `StemPack` only math relations; the same
  statement is never checked twice.
- **Sentences.** Statements are split by the STEM segmenter, so CORE-QNT-001 sentence numbers
  match the STEM claims.

`CorePack(reading)` uses `reading.view` for three things:
- the quotation reading (CORE-SRC-003, -004, -005), where inch and arcsecond marks attached to
  numbers (`12″`, `0.5"`) are masked, so CORE-SRC-004 no longer fires on them;
- chronology, so `1500 K` is never a year;
- CORE-SELF-001 and `_sentences_with_paragraph`.

CORE-SRC-001 (per `source_ref`) is unchanged. The default `GENERAL` keeps every other branch
unchanged.

---

## 13. Performance

- **Front end.** Linear in the response length: one lexer pass per span, a bounded parser,
  and no backtracking regex on unbounded text. The document is built once per (text,
  request, profile) and shared by parser, pack and CorePack.
- **Engine.** About 4 to 20 ms per check, measured on today's probes. Probe totals:
  - 40 linear arithmetic checks: 327 ms;
  - a five-interval nonlinear Form S check: 8 to 9 ms;
  - nonlinear rearrangement, square-root and solution-set checks: 5 to 15 ms each;
  - a 150-step derivation (150 checks) through the hub: about 0.95 s.
- **Budget.**
  - At most 128 STEM checks per report (ST-LIM-002 beyond).
  - Nonlinear checks run with a deterministic `rlimit` (`NONLINEAR_RLIMIT`, calibrated in
    stage `engine`), and their cutoffs read as undecided.
  - A per-report wall-clock guard of 8 s for STEM checks marks the remaining checks undecided
    (INT-SUBJ-002, "check budget"). It only ever degrades to undecided, never to success.
- **Targets** (asserted by stage `corpus-eval` stress tests, `-m stress`):
  - p95 hub receive for a typical 3-part Physics answer below 250 ms;
  - a 128-check answer below 2.5 s;
  - an adversarial 400,000-character input (nested brackets, unclosed `$`, `1e1e1e`, 30-digit
    numbers) through the front end below 1.5 s;
  - unchanged suite time for the non-STEM tests.

---

## 14. Safety (no eval)

- **No string evaluation.** No `eval`, `exec`, `compile`, `__import__`, `importlib`, `pickle`,
  `marshal`, `sympify`, `parse_expr`, `ast.literal_eval`, `subprocess` or `os.system`, and no
  library that evaluates strings. No sympy dependency.
- **`Fraction` input.** `Fraction` is constructed only from integer pairs, or from digit
  strings the lexer has already validated.
- **Enforcement.** A test (`tests/stem/test_front_end_safety.py`) parses the source of
  `stem/`, `adapters/stem_specialist/` and `branches/stem_pack.py` with the standard `ast`
  module and fails on any forbidden name, attribute or import. Imports are allowlisted:
  - from the standard library: `re`, `fractions`, `dataclasses`, `functools`, `typing`,
    `hashlib`, `unicodedata`, `math` (enclosure cross-check only), `enum`;
  - from the package: `epinoic_logic.ir.schema`, `epinoic_logic.translate.contracts`,
    `epinoic_logic.engine.policies` and their siblings.
- **Closed outputs.** Only allowlisted AST nodes are translated, and only into IR 1.0 nodes.
  `Problem.model_validate` runs on every built problem, and the validator runs again inside
  `verify`.
- **Bounded work.** Every loop is bounded by `StemLimits` (section 4.9). Recursion depth is
  checked before descent, and exponent and digit bounds prevent `Fraction` blow-up
  (`10^999999`).
- **Code is inert.** Code spans are never parsed for meaning, run, imported or written to disk.
- **Verbatim original.** `original_response` is never altered.
- **Trust.** The engine discards any `verified=True` in untrusted payloads (E505). The STEM
  pack builds problems in-process, as quant does, and agent self-reports stay advisory.
- **Repository rules.** No code or prompt text is copied from other projects. No model names
  or session ids appear in code or docs.

---

## 15. Out of scope

1. The truth of laws, data, constants or definitions, and whether a model applies or is
   physically valid (the evidence service and subject evaluator).
2. Symbolic calculus (derivatives, integrals, limits, series, differential equations): named
   undecided (ST-UNDEC-001), never decided.
3. Vectors, matrices, complex numbers, factorials or combinatorics written with `!`, Σ with
   symbolic bounds, probability distributions, and asymptotic notation: named undecided.
4. Exact proof of identities between transcendental values. Enclosures establish agreement to
   10⁻¹⁵ relative only, and the description says so.
5. Unit correctness beyond dimension consistency (warnings) and explicit conversion checks.
   Significant-figure policy (penalising too many figures) is not checked.
6. Molar masses from formulas and any check against our own data tables, except the D3
   readings. Constants are used only to widen a written value or, at warning severity, to read
   an unstated standard symbol.
7. Program behaviour. Code is never executed, interpreted or checked (ST-CODE-001 info).
   Algorithm quality and complexity claims are not checked.
8. Diagrams, graphs, sketches, images and handwriting; reading values from a graph.
9. The completeness or quality of the method, presentation and mark-scheme matching. Only a
   show-that target value is compared (warning).
10. Uncertainty-propagation rules. Their arithmetic is checked as arithmetic; whether the
    right rule was used is not.
11. Cross-agent symbol unification in the model-translator pool (`integrity/cross_check.py`).
    Deterministic STEM checks are not pooled. The STEM profile text asks the translator to
    namespace symbols per claim, but no glossary rule changes.
12. Quotation-grounding normalisation of minus, en dash and × in `translate/grounding.py`.
    It is deferred; STEM answers rarely quote supplied texts.
13. Adding the Limits digest into `Binding.binding_digest`. The engine records non-default
    Limits on the signed result instead, which keeps the hand-off binding formula unchanged. A
    later provenance change may bind them.
14. Non-SI conventions beyond the table (imperial units except °F and the inch mark), and
    locale number formats beyond the decimal-comma rule.

---

## 16. Test plan

New tests are added. No existing test is weakened or deleted. The two recorded routing
assertions (section 10.2) are replaced by assertions of equal strength.

**Stage `core`** (no engine). `tests/stem/`:
- `test_normalize.py`: the length-preserving map; masked views keep offsets; quotation and
  inch marks inside spans are masked.
- `test_spans.py`: every span kind; `$` versus currency; derivation-line continuation;
  tables; truth-table blocks; code spans recorded and masked.
- `test_segment.py`: `The ball falls 5.0 m. It then stops.` splits; `is v. Then` splits;
  `c. 1500` and `p. 12` do not split; `\frac{1}{2} M v^2` is never cut; History splitter
  outputs are byte-identical on the History corpus.
- `test_lexer.py`: every number form in 4.4; Unicode minus; superscripts and subscripts;
  LaTeX allowlist; an unknown command is Unparsed.
- `test_numbers.py`: significant figures, last place, half-width, the integer trailing-zero
  rule, exactness, a bare zero.
- `test_units.py`: prefixes, `ms` versus `m s`, unit expressions, the ambiguity table per
  profile, exact factors, affine handling, dimensions.
- `test_parser.py`: precedence, right-associative powers, implicit multiplication against
  scope (`at`, `mgh`, `½mv²`, `2πr`), two readings, ST-PARSE-002 at three, Unsupported
  reasons, depth and node bounds.
- `test_scope.py`: binding sources, rebinding, any-binding matching.
- `test_relations.py`: link classification for every row of 4.7; deterministic check ids;
  claim ids.
- `test_chem_parse.py`, `test_boolean_parse.py`: tallies, hydrates, charges, fractional
  coefficients, truth tables, based numerals.
- `test_document.py`: memoisation keys; one document shared by every reader.
- `test_front_end_safety.py`: the AST scan of section 14; adversarial inputs within time bounds.

**Stage `engine`.** `tests/engine/`:
- `test_pack_policies.py`:
  - the named policies map to exact Limits;
  - an unknown name is refused;
  - a default-policy result has no `limits` field and an unchanged signable text;
  - a nonlinear result records its Limits under the signature, so tampering fails
    `verify_signature`;
  - the hand-off binding check is unaffected;
  - `NONLINEAR_RLIMIT` turns a hard polynomial system into TIMEOUT or UNKNOWN, never success.
- `test_stem_shapes.py`: every STEM encoding shape through `verify` with its expected status.
  - Linear: Form E pass and fail; the sign-aware band at −9.8 against −9.81; zero; an
    auxiliary closed divisor; Int balance; a Boolean identity by satisfiability; inequality
    steps; enclosure Form S.
  - Nonlinear: a surd; a symbolic divisor; rearrangement correct and wrong; completeness of a
    solution set, complete and with a missing root; a decimal root; Form S with five
    intervals.
  - Each shape is UNSUPPORTED (E201) under `linear` where it is nonlinear.
  - Median time per shape below 50 ms.

**Stage `checks`.** `tests/stem/`:
- `test_constants.py`: table integrity; written-constant recognition; the dimension guard of
  D3b.
- `test_enclosures.py`: enclosure width and containment against `math`, over grids including
  special angles, at both ends of the bounds; the exact table.
- `test_scaling.py`: the factoring identity on random monomials and sums; literals at most 40
  digits; ST-LIM-001 beyond.
- `test_tolerance.py`: R1 to R10, including the integer trailing-zero rule and the observed
  case.
- `test_to_ir.py`: every row of 7.4; symbol naming is injective; grounding kinds per premise;
  `Problem.model_validate` passes; policy chosen exactly when needed.
- `test_checks_engine.py`: every check kind of 8.1, correct and wrong, through `verify`, with
  expected status, `failure_severity`, `claim_ids` and description bounds.
- `test_checks_no_false_errors.py`: rounding to the written precision; booklet constants
  (9.8 against 9.81; 6.6 against 6.63 × 10⁻³⁴); carried intermediates (4.85 → 4.9);
  approximate chains; conversions inside chains (`0.0125 m³ = 12.5 dm³`); bare conversion
  factors (`÷ 3.6`); percentages both ways; physics positive roots; sign conventions
  (g = −9.81); part (b) reusing part (a)'s letters. None may yield a failed check.
- `test_checks_safety.py`: undefined expressions give ST-UNDEF-001 with no problem built; no
  free symbol in a Form S problem; literal bounds.

**Stage `branch`.**
- `tests/stem/test_parser_claims.py`: claims are offset substrings; ids are stable; roles and
  materiality per 9.2; empty text raises; a code-only answer yields claims; data lines and
  tables are kept; INT-REQ-012 never fires on a derivation.
- `tests/branches/test_stem_pack.py`: ST findings with codes and severities; check ids match
  the parser's assumption text; nothing on `The speed is 15 m/s.`; ST-INTERNAL-001 on an
  injected failure.
- `tests/branches/test_stem_routing.py`: every alias of 10.1; word boundaries; the misroutes
  fixed; `Physics/Chemistry` → stem; every display name; unknown → generic; packs[0] is core.
- `tests/branches/test_quant_si_reading.py`:
  - the false errors fixed: `500 mm to 2 m`, `2 kg to 500 g`, `halved twice`, `300 K`,
    `3.0 A to 1.5 A`;
  - a negative and a signed change;
  - GENERAL byte-identical on the History, Economics and Business corpora.
- `tests/channel/test_branch_check_mapping.py`: the status mapping table of 11.2 for
  ENTAILED, SATISFIABLE and UNSATISFIABLE expectations; E108; INCONSISTENT_PREMISES under both
  flags; INT-SUBJ-004; claim ids; truncation of a 5,000-character description; BR-INTERNAL-001
  on a raising pack; an unknown policy.
- `tests/channel/test_stem_channel.py`:
  - the observed case end to end (INT-SUBJ-001 on the chain claim, delivered);
  - the 13 probe answers;
  - echo exemption for show-that answers;
  - coverage on symbol-only answers;
  - STEM imperatives split items;
  - the LaTeX word count;
  - relay (`req=None`).
- `tests/translate/test_stem_subjects.py`, `tests/translate/test_stem_eligibility.py`: the
  profiles, the prompt profile text, and rule 4 with relation signs.
- `tests/integrity/test_stem_ledger_figures.py`: scientific-notation figures; plain figures
  unchanged.
- `tests/e2e/test_stem_e2e.py`: multi-agent Physics + Maths + combinator through `RouterHub`;
  receipts signed; the scope tail present.
- The full existing suite stays green.

**Stage `corpus-eval`.**
- `tests/stem/data/stem_corpus.json`: at least 120 correct answers across Physics, Chemistry,
  Biology, ESS, SEHS, Design Technology, Mathematics AA/AI and CS, in LaTeX inline and
  display, Unicode, ASCII and mixed prose, plus at least 240 mutants.
- **Mutation classes** (F's fault catalogue, D14), each mapped to its expected code, check
  kind and claim id:
  - arithmetic slip;
  - wrong operator;
  - power-of-ten error;
  - wrong substitution;
  - dropped factor (½, 2);
  - wrong rearrangement;
  - lost root;
  - unit-conversion error;
  - wrong prose restatement;
  - unbalanced equation (atom and charge);
  - wrong Boolean identity;
  - wrong truth-table row;
  - wrong base conversion;
  - sign error;
  - wrong comparison;
  - misstated given;
  - show-that target mismatch;
  - dimension error (warning);
  - plus rounding-only "mutants" that must pass.
- `tests/stem/test_corpus.py` acceptance criteria:
  - every correct answer: no INT-SUBJ-001, no INT-SUBJ-003, no INT-SUBJ-004, no error of any
    kind, and the original delivered verbatim;
  - every mutant in a decidable class: INT-SUBJ-001 (or the warning code its class
    specifies) on the right claim with the right check kind;
  - every relation in an out-of-scope class: named undecided with its reason;
  - the undecided rate on correct answers is reported per subject and stays under 10 % of
    relations;
  - the 13 silent passes observed today are all caught or named.
- `scripts/arena/stem_mutations.py` and `scripts/arena/run_arena.py`: STEM subjects and
  mutation injection in the arena harness for contained multi-agent runs. Overseer audits
  read receipts only.
- `tests/stress/test_stem_stress.py` (`-m stress`): the targets of section 13.
- `docs/STEM_RESULTS.md`: the measured results of the contained run, with no claims beyond
  them.

---

## 17. Implementation stages (sequential; disjoint files)

`core` and `engine` may run in parallel. `checks` needs both. `branch` needs `checks`.
`corpus-eval` needs `branch`. Each stage ends with the full suite green, plus an overseer
audit of its own tests. No stage writes a file another stage owns.

### Stage `core`: math front end (no engine changes)

- `src/epinoic_logic/stem/__init__.py`
- `src/epinoic_logic/stem/README.md`
- `src/epinoic_logic/stem/limits.py`
- `src/epinoic_logic/stem/normalize.py`
- `src/epinoic_logic/stem/spans.py`
- `src/epinoic_logic/stem/segment.py`
- `src/epinoic_logic/stem/lexer.py`
- `src/epinoic_logic/stem/numbers.py`
- `src/epinoic_logic/stem/units.py`
- `src/epinoic_logic/stem/nodes.py`
- `src/epinoic_logic/stem/parser.py`
- `src/epinoic_logic/stem/scope.py`
- `src/epinoic_logic/stem/relations.py`
- `src/epinoic_logic/stem/chem.py`
- `src/epinoic_logic/stem/boolean.py`
- `src/epinoic_logic/stem/document.py`
- `tests/stem/__init__.py`
- `tests/stem/test_normalize.py`
- `tests/stem/test_spans.py`
- `tests/stem/test_segment.py`
- `tests/stem/test_lexer.py`
- `tests/stem/test_numbers.py`
- `tests/stem/test_units.py`
- `tests/stem/test_parser.py`
- `tests/stem/test_scope.py`
- `tests/stem/test_relations.py`
- `tests/stem/test_chem_parse.py`
- `tests/stem/test_boolean_parse.py`
- `tests/stem/test_document.py`
- `tests/stem/test_front_end_safety.py`

Exit: the front end reads every probe answer into a document with the expected statements,
ASTs, scope and planned check ids. The safety scan passes.

### Stage `engine`: named pack policies and the policy record (no IR schema change, no compiler change)

- `src/epinoic_logic/engine/policies.py` (`PACK_POLICIES = {"linear": DEFAULT_LIMITS,
  "nonlinear": Limits(allow_nonlinear=True)}`, `policy_limits(name)`, `NONLINEAR_RLIMIT`)
- `src/epinoic_logic/engine/results.py` (`VerificationResult.limits: Optional[Limits] = None`,
  set only when the Limits differ from `DEFAULT_LIMITS`; omitted from dumps when None, so
  existing results and signatures are byte-identical)
- `src/epinoic_logic/engine/runner.py` (records the non-default Limits on every result path)
- `src/epinoic_logic/engine/README.md`
- `tests/engine/test_pack_policies.py`
- `tests/engine/test_stem_shapes.py`

Exit: every encoding shape of sections 5 and 7 is decided as expected under its named policy,
within time; default results are unchanged.

### Stage `checks`: AST to IR, the checks, and the data-booklet and constants tables

- `src/epinoic_logic/stem/constants.py`
- `src/epinoic_logic/stem/enclosures.py`
- `src/epinoic_logic/stem/scaling.py`
- `src/epinoic_logic/stem/tolerance.py`
- `src/epinoic_logic/stem/to_ir.py`
- `src/epinoic_logic/stem/checks.py`
- `src/epinoic_logic/stem/ENCODINGS.md`
- `tests/stem/test_constants.py`
- `tests/stem/test_enclosures.py`
- `tests/stem/test_scaling.py`
- `tests/stem/test_tolerance.py`
- `tests/stem/test_to_ir.py`
- `tests/stem/test_checks_engine.py`
- `tests/stem/test_checks_no_false_errors.py`
- `tests/stem/test_checks_safety.py`

Exit: every check kind of section 8.1 is built as a `PlannedCheck` and decided correctly
through `verify`. No false error appears on the no-false-error set. Undecided cases carry the
right ST code.

### Stage `branch`: parser, pack, registry, profiles, eligibility, channel, end to end

- `src/epinoic_logic/adapters/stem_specialist/__init__.py`
- `src/epinoic_logic/adapters/stem_specialist/parser.py`
- `src/epinoic_logic/adapters/README.md`
- `src/epinoic_logic/stem/si_reading.py`
- `src/epinoic_logic/stem/hub_hooks.py`
- `src/epinoic_logic/branches/stem_pack.py`
- `src/epinoic_logic/branches/base.py`
- `src/epinoic_logic/branches/registry.py`
- `src/epinoic_logic/branches/packs.py`
- `src/epinoic_logic/branches/quant.py`
- `src/epinoic_logic/branches/README.md`
- `src/epinoic_logic/channel/bus.py`
- `src/epinoic_logic/channel/request_parser.py`
- `src/epinoic_logic/channel/README.md`
- `src/epinoic_logic/translate/subjects.py`
- `src/epinoic_logic/translate/eligibility.py`
- `src/epinoic_logic/integrity/ledger.py`
- `src/epinoic_logic/integrity/README.md`
- `src/epinoic_logic/version.py`
- `README.md`
- `tests/stem/test_parser_claims.py`
- `tests/branches/test_stem_pack.py`
- `tests/branches/test_stem_routing.py`
- `tests/branches/test_quant_si_reading.py`
- `tests/branches/test_hub.py` (line 46 only: recorded behaviour change)
- `tests/branches/test_quant_and_packs.py` (line 76 only: recorded behaviour change)
- `tests/channel/test_branch_check_mapping.py`
- `tests/channel/test_stem_channel.py`
- `tests/translate/test_stem_subjects.py`
- `tests/translate/test_stem_eligibility.py`
- `tests/integrity/test_stem_ledger_figures.py`
- `tests/e2e/test_stem_e2e.py`

Exit: the observed case and the 13 probe answers behave as section 16 states. The suite is
green. The stage report lists the two routing assertions.

### Stage `corpus-eval`: corpus, arena mutations, stress

- `tests/stem/test_corpus.py`
- `tests/stem/data/stem_corpus.json`
- `scripts/arena/stem_mutations.py`
- `scripts/arena/run_arena.py`
- `tests/stress/test_stem_stress.py`
- `docs/STEM_RESULTS.md`

Exit: the acceptance criteria of section 16 are met and measured; the results are written
with no claim beyond what was run.

---

## 18. Version bumps and recorded behaviour changes

All version bumps are made in stage `branch`, in `version.py`:
- **ENGINE_VERSION:** the result records non-default Limits (stage `engine`).
- **POLICY_VERSION:** named pack policies; alias and word-boundary changes; the new `stem`
  profile; eligibility rule 4.
- **TRANSLATOR_VERSION:** the STEM profile text.

IR_VERSION stays 1.0.

Recorded behaviour changes, for the overseer audit and the user's sign-off:
1. STEM subjects route to the `sciences`, `mathematics` and `computer_science` branches
   instead of `generic`, which changes two existing assertions (section 10.2).
2. A branch check whose ENTAILED result carries E108 is now undecided, not ok.
3. A check expecting UNSATISFIABLE that comes back SATISFIABLE is now failed, not undecided.
4. Subject aliases match on word boundaries.
5. INT-SUBJ-001 and INT-SUBJ-002 now carry claim ids.
6. New codes: INT-SUBJ-004 and BR-INTERNAL-001.

Every other non-STEM behaviour is unchanged by construction (P5).
