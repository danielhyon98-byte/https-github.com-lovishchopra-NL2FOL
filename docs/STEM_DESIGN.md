# STEM support: design

**Status: IMPLEMENTED on branch `stem-build`; not yet merged.** All five stages of section 17
(`core`, `engine`, `checks`, `branch`, `corpus-eval`) are in the code, and the full suite passes
(docs/STEM_RESULTS.md). The review rounds (overseer audits of each stage) and the STEM arena with
live specialists were **not run in this build**: the STEM build is run as one integrated system
with the main arena, which merges this branch (round 7 when it is ready, otherwise round 8) and
tests STEM there with a STEM lens and a STEM fixer. This document was revised after
implementation to match the code; where the code refined the original design, the text below
states what the code does (and section 19 lists the refinements).

This document synthesises two independent designs: the representation-outward design (R) and
the fault-outward design (F). R builds a math front end first and derives the checks from what
it reads. F starts from the faults the hub let through before STEM support and builds an engine
encoding for each. Where they disagreed, section 2 records the decision and the reason. Sections
17 and 18 split the implementation into five sequential stages that touch disjoint files.

Evidence used at design time came from read-only probes run against this worktree before
implementation (baseline suite then: 1067 passed, 12 deselected). The encodings in sections 5 and
7 were each run through `engine.runner.verify`. Each took 4 to 20 ms. Forty arithmetic checks in
a row took 327 ms. Measured results of the implementation are in docs/STEM_RESULTS.md.

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
2. **Decided or named.** Every relation the front end recognises ends in exactly one outcome
   (`stem/relations.py`):
   - `check`: an engine check;
   - `undecided`: a finding that names it as undecided and gives the reason;
   - `binding` (a value stated for a symbol, `m = 2.0 kg`), `formula` (a stated law or
     definition, `F = ma`; its truth is out of scope) or `context` (a relation with no premise
     to check it against, such as the first line of a derivation or a domain condition
     `x > 3`): recorded, not checked.
   Nothing recognised is dropped silently.
3. **Right code, right severity.** Every fault the infrastructure can see is named on the
   receipt with a stable code and a documented severity.
4. **No false errors.** Error severity comes only from an engine result about a relation that
   rests solely on what the report and the request state, or on exact encoding devices. If
   the reading or the tolerance could be wrong, the outcome is a disjunction of readings or a
   warning, never an error.

**Scope statement** (`stem.tolerance.STEM_SCOPE`, the first sentence of every STEM problem's
`notes`; every receipt summary still ends with the channel's `_SCOPE_TAIL`): a STEM check
proves a property of its encoding only. It proves that
the written arithmetic, substitution, conversion, algebraic step, balance or Boolean identity
holds, or does not hold, under the stated premises, the documented readings and the STEM
tolerance rule. It does not establish any of the following:
- that a law applies;
- that data are true;
- that a model is physically valid;
- that a unit is the right one beyond the dimension and conversion checks named here;
- that the answer is what the question wanted.

The engine's `SCOPE_STATEMENT` applies unchanged.

**Observed before STEM support, and now.** Before this work a Physics answer
`a = (20 - 0)/4.0 = 6.0 m s⁻²` (true value 5.0) went to the generic branch and crossed the hub
ACCEPTED, with no finding and no formal check.

With STEM support the same answer (fixture `stem-phys-001`):
- goes to the `sciences` branch;
- gets a `stem-eq-1` check whose engine status is COUNTEREXAMPLE, with model `c = 5`, `r = 6`;
- receives INT-SUBJ-001 (error) naming the claim that holds the chain (`s1.2`), with the
  computed and stated values in the message;
- is still delivered (ACCEPTED_WITH_FINDINGS).

Of 13 deliberately wrong probe answers, only 1 had its equation error caught before STEM
support. The test plan (section 16) requires every one to be caught or named, and
`tests/stem/test_corpus.py` asserts that all 13 now are.

---

## 2. Synthesis decisions (conflicts resolved)

| # | Point | R (representation-outward) | F (fault-outward) | Decision |
| --- | --- | --- | --- | --- |
| D1 | Linear or nonlinear | Allow nonlinear (`allow_nonlinear`) per check whenever a product of two unknowns appears. | Keep every check linear: substitute the stated value as a literal coefficient (`σ·s` for `s²`; plug in a stated root). | **Linear by default.** A check is nonlinear only when its encoding really multiplies two unknowns: exact surds, symbolic algebra steps, completeness of solution sets, and the interval form with two or more interval operands. F's literal-substitution trick is kept for exactly one job: a stated root is checked by substituting it into the equation (linear membership). It is not used as a general device, because it bakes the value under test into the coefficients and does not compose. |
| D2 | How the nonlinear policy reaches the engine | `FormalCheck.limits: Optional[Limits]`, any value allowed. | Not needed. | **A named policy, not raw Limits.** `FormalCheck.policy` is either `"linear"` or `"nonlinear"`. The engine maps the name to a fixed `Limits` (`engine/policies.py`), so a pack can never raise `max_nodes`, the digit count and so on. The engine records any non-default Limits on the signed result. Implemented: `PACK_POLICIES` is read-only; `nonlinear` is `Limits(allow_nonlinear=True)` and nothing else; `policy_config` caps the solver's `rlimit` at `NONLINEAR_RLIMIT` (2,000,000); and the runner refuses any assertion of polynomial degree above `NONLINEAR_MAX_DEGREE` (24) with E201 before compiling, because Z3 could not be interrupted inside very high-degree polynomials. |
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
| D14 | Fault catalogue | Derived from the grammar. | The 13 silent passes and the false errors observed before STEM support. | **F's catalogue becomes the mutation corpus.** It is the acceptance bar for stage `corpus-eval` (section 16). |

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
StemTextParser.parse_response ──┐   (the channel passes it the request text: accepts_request_text)
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
  diverge. The document is memoised in an `lru_cache(64)`; `StemPack` also keeps its own
  32-entry cache of (findings, formal checks) per report and request.
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

  `CorePack()` with the default `GENERAL` reading runs the pre-STEM code path byte for byte. English,
  History, Psychology, Economics, Business Management and generic are therefore unchanged. The
  shared edits in section 11 are additive, and their defaults reproduce the pre-STEM behaviour.
- **P6. The original is verbatim.** Normalisation happens only in a reading view of the same
  length, a 1:1 character map. Claim texts are offset substrings of the original, truncated to
  the contract (4000 characters).

### 3.3 Module layout

New subpackage `src/epinoic_logic/stem/`. It is the front end and the encodings. It imports
nothing from `branches/`, `channel/`, `engine/` or `ir/`: problems leave it as plain IR data
(`dict`) that `StemPack` validates. The one module outside the package it reads is the shared
sentence splitter `adapters/history_specialist/sentences.py` (section 4.3).

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

- U+2212 (minus) and U+2011 (non-breaking hyphen) become `-`.
- NBSP, U+2007, U+2009, U+200A and U+202F become a space. Zero-width characters (U+200B,
  U+200C, U+200D, U+2060, U+FEFF) also become a space, so a hidden character can split a token
  but never silently join two.
- U+22C5 and U+2219 become U+00B7, which is a multiplication marker in math and unit context and
  a hydrate dot in a chemical formula. U+2217 becomes `*`, and U+2126 (ohm sign) becomes `Ω`.
- U+00D7 `×` stays its own token.
- An en dash U+2013 or figure dash U+2012 is read as minus only after the start, a space, an
  operator, `(` or a relation sign, and before a digit or letter. `3–5 s` between two numbers
  stays a dash (a range: Unsupported, named), and so does `H–H`.
- Superscript digits and signs (⁰ to ⁹, ⁺, ⁻) and subscripts (₀ to ₉) are tokenised as they
  stand. Nothing is expanded. Letters of other scripts are left alone, so a Cyrillic `а` that
  looks like a Latin `a` is never read as one: the lexer rejects it.

The prose view masks every math span and every quantity carrying a unit with a placeholder of
the same length: an upper-case first character, then filler that is not a space, punctuation,
quotation mark or digit. The shared splitter can start a sentence at a masked span. It never
splits inside one, and it never sees a decimal point, prime, inch mark or quotation mark
inside one.

### 4.2 Spans (`spans.py`), extracted in this order

1. **Code.** Fenced ` ``` ` and `~~~` blocks (the language tag is kept; an unclosed fence runs
   to the end), inline `` `code` ``, and 4-space indented blocks in the `computer_science`
   profile. A code span is masked from maths and prose, and it is never parsed for meaning or
   run (ST-CODE-001 names it).
2. **LaTeX display.**
   - `$$…$$` and `\[…\]`;
   - the environments `equation`, `equation*`, `align`, `align*`, `gather` and `gather*`; an
     inner `aligned`, `split` or `gathered` wrapper is read through.

   Rows are split at `\\`, and `&` is dropped by the parser.
3. **LaTeX inline.** `$…$` and `\(…\)`, following TeX convention: the content is non-empty,
   has no leading or trailing space, closes in the same paragraph, is not followed by a digit,
   and is at most `max_span_chars` long. `\$` and an unclosed `$5 per kg` are currency.
4. **Chemical equations** (chemistry profiles): an arrow with species on both sides.
5. **Unicode or ASCII runs in prose.** A maximal run the math lexer can tokenise that
   contains a relation sign. It starts at an identifier, a number, `(`, `|` or a minus after a
   clean boundary, or at a relation sign right after a prose label (`Energy absorbed = 4 × 414
   + …`) or at the start of a line (a continuation). It stops before a prose word (three or
   more letters that are not a function name, a unit after a number, a Greek name or a name in
   scope, or a short English word such as `is`, `so`, `or`), before sentence punctuation, a
   comma or semicolon outside brackets, a quotation mark or a bracket it did not open. A run
   that opens with a bracket and holds its relation sign only inside it is read again from
   inside the bracket, up to three brackets deep. A number with a unit and no relation sign is
   kept as a `quantity` span (masked in the prose view, read as a prose value).
6. **Verbal arithmetic.** `<number> (plus | minus | times | multiplied by | divided by)
   <number> … (equals | is equal to | gives | makes) <number>`, with numbers only and no
   symbols. It is read as the same AST.
7. **Tables and data lines.** Markdown tables and bracketed data, vector and list lines
   (`[1, 2]`, `{2, 3}`) become text claims. A truth-table block (section 4.8) is recognised from
   a table's header row and rows of 0/1 or T/F. A JSON receipt shape (string keys) keeps the
   shared JSON rule. A block of lines that open with `|` is a table only when it has a table's
   structure: a Markdown delimiter row under its header (`|---|---|`), or the shape of a truth
   table written without one. Bars that only enclose an expression are maths, read like any
   other line: an absolute value (`|−2| = 2` is checked as `$|−2| = 2$` is), a norm, a
   determinant written with bars (section 22, S7).

Derivation lines are statements, not spans: a line is a derivation line when at least 60 % of
its non-space characters lie in one math span, and a line that begins with a relation sign
continues the previous line's chain (section 4.3). Markup (emphasis markers, heading lines, list
markers, block-quote marks, part labels at the start of a line) is recorded for blanking in the
math view. Every scan is linear: `$` signs are paired through a precomputed table, prose lines
are lexed in windows of at most `max_line_chars` characters, and the only regular expressions
are anchored, bounded line-start patterns.

### 4.3 Statements (`segment.py`)

A statement is one of the following:
- a sentence of the prose view;
- a derivation line;
- a display row;
- a list item;
- a code block;
- a table.

Sentences come from the shared `sentence_boundaries` with three STEM-only boundary rules:

- after `<number> <unit>.` and after a masked span followed by `.`, a space and a capital
  (also when a unit follows the masked span, `… $E = 3.5$ J. Next …`, through a bounded
  look-back of 16 characters);
- after a single lower-case letter that is a symbol in scope, followed by `.`, a space and a
  capital (`the speed is v. Then …`);
- neither rule applies to `c.` or `p.` followed by a digit (circa, page).

Part labels (`(a)`, `b)`, `(b)(ii)`, `Part (c)`, `Question 2`, Markdown headings) are recorded
as structure, not claims, and scope a part's checks. A Markdown heading, or a part label alone
on its line, starts a paragraph. A list item holding several sentences is split into them.
Statement ids are `s<paragraph>.<statement>`, both counted from 1; statements beyond
`max_statements` merge into one `s.tail`. History's splitter and its `ABBREVIATIONS` are
untouched; the wrapper lives only in `stem/segment.py`.

Since the merge with the round-7 development branch, the line rules are the generic parser's
(section 20.1): an equation continued on lines that open with `=` is one statement, label-only
lines and mark annotations are furniture, and a table is one statement per row.

### 4.4 Lexer (`lexer.py`): one forward pass, no backtracking regex

- **NUMBER.**
  - Digits with an optional decimal point.
  - A decimal comma only when 1 or 2 digits follow and no space follows outside a coordinate
    pair.
  - Thousands groups with `,`, a thin space or the LaTeX thin space `\,` (`21\,131.40`), in groups
    of exactly three, one kind of separator throughout (section 21).
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
- **OP and REL** tokens (REL also takes `≡` and `∝`), grouping `() [] {}`, COMMA, PERCENT,
  DEGREE `°`, primes `′ ″` (arc minutes and seconds or inches only directly after a number),
  ABS bars, `!`, ratio `:` between numbers, a magnification suffix `×` after a number at the end
  of an operand, and the Boolean operators `∧ ∨ ¬ ⊕` and words `AND OR NOT XOR` (the words in CS
  only).
- **UNSUP** marks the start of a construct outside the encodings, with its reason (`∫ Σ ∏ ∂ ∇
  lim d/dx \int \sum \lim \vec \mathbf \partial \binom \ldots`, matrices); **ERROR** is an
  unknown LaTeX command or a letter of another script (a confusable). The lexer never raises,
  and every token records whether space preceded it, so `m s` (metre second) and `ms`
  (millisecond) stay different.

### 4.5 Grammar (`parser.py`): Pratt, lowest to highest precedence

```
sequence  := chain ( connective chain )*        connective: ⇒ ∴ , ; or and so hence gives ... (\text{or})
chain     := expr ( relop expr ){1,12}          (a chain may open with a relop: a continuation or a prose label)
relop     := = | ≈ | ≃ | ~ | ≡ | ≠ | < | > | ≤ | ≥ | <= | >= | ⇒ | ∴ | → | ⇌ | ⇔ | \approx | \neq | \leq | \geq | \Rightarrow
             (→ and ⇌ are reaction arrows only in chemistry mode between two species lists; ⇔ is Boolean equivalence only in CS)
expr      := term ( ( + | - | ± | ∓ ) term )*
term      := unary ( ( × | · | * | / | ÷ | \cdot | \times | \div | juxtaposition ) unary )*
unary     := ( - | + | ± | ¬ ) unary | power
power     := postfix [ ( ^ | ** | superscript ) exponent ]           right-associative
exponent  := signed integer literal (|n| ≤ 12; up to 1000 over a closed base) | ½ | 1/2   (½ is read as a square root)
postfix   := primary [ % | ° | ! | × (magnification) | base subscript ]
primary   := number [unit] | symbol | func_app | ( expr ) [unit] | { expr } | [ expr ] (concentration in chemistry)
           | \frac{expr}{expr} | \sqrt{expr} | √primary | √(expr) | | expr | | ratio
unit      := unit_expr                 (after a space, or \text{…}/\mathrm{…}, Ω, °C; the unit must end the operand:
                                        next is an operator, a relation, a close, a separator or the end)
ratio     := number : number           (only directly beside a relation sign: a:b = c:d)
func_app  := FUNC ( (expr) | {expr} | primary )
```

A glued unit (`1.5kg`) is read only for a common multi-letter unit that does not also split
into names in scope, so `2as` stays `2·a·s`. After a known unit atom, an unknown atom with an
exponent (`yr⁻¹`) is kept as an unknown unit (ST-UNIT-001). A broken bound or an unreadable
operand makes that operand an error (ST-LIM-001 or ST-PARSE-001) and the parser resynchronises
at the next relation sign; an unknown LaTeX command or a confusable letter makes the whole span
Unparsed (ST-PARSE-001, the command named). Nothing raises out of `parse_math`.

A power whose exponent is no integer is one value, a `RealPower`, when its base and its exponent
are both closed and carry no unit (`10^(−8.2)`, `10^(8.2 − 7.8)`, `(3465/250)^(1/6)`): figures,
signs, brackets and `\frac` in the exponent, no symbol, unit, angle or per cent in either
(section 21). So is an integer power beyond 12, up to 1000, of a closed base with no unit
(`(1 + 0.065/12)^{-60}`, `1.003^{144}`, `2^{20}`).

Unsupported, each as a named `Unsupported(reason)` node (the relation that holds one is
ST-UNDEC-001 with the reason):
- a symbolic power, a non-integer power of anything but a closed value with no unit, an integer
  power beyond 12 of anything but a closed value with no unit (and any beyond 1000), a cube root;
- `!`;
- `Σ` (except over integer bounds with at most 24 terms, which is read as its terms), `∫` and
  `lim`;
- `d/dx` and `dy/dx`;
- `f′(x)` and `f''(x)` (derivative; the node keeps the function's name and argument);
- vectors in bold, arrows or `\vec`;
- matrices, and a tuple `(x, y)`;
- `i` beside a number or `±` (complex number);
- asymptotic notation (`O(…)`, Computer Science);
- an evaluation bracket `[F(x)]₀²` and infinity.

### 4.6 Implicit multiplication and scope

- **Segmentation.** A letter run inside a math span is segmented by the longest prefix over
  the names in scope:
  - declared symbols;
  - formula left-hand sides;
  - the STEM name table (`parser.STEM_NAMES`: `KE PE GPE EPE EMF emf pH pOH pKa pKb Ka Kb Kw
    Kc Kp Mr Ar NA Ek Ep RMM RFM NPP GPP SV HR BMI RQ`);
  - function names.

  A name pre-pass (`scope.prescan_names`) collects the names a text declares before anything
  is parsed: a letter run directly before `=` or `≈` at the start of a relation (`PV = 5000`),
  and every subscripted, primed or Δ-prefixed symbol and Greek letter. With scope
  `{u, v, a, t}`, `at` is `a·t`; `mgh` is `m·g·h`; `½mv²` is `½·m·v²`; `2πr` is `2·π·r`. A run
  that matches no name splits into single letters, except an all-capital run of three or four
  letters (`GPP`), which is one name; a run longer than `max_letter_run` (12) is one unknown
  symbol. If two segmentations both match the scope, both are kept as readings (at most 2);
  with more readings, ST-PARSE-002.
- **Numbers, units and symbols.**
  - A number followed by a space and a unit token is a Quantity when the unit token ends the
    operand.
  - A number directly followed by a declared symbol is multiplication.
  - A letter at the start of an expression is a symbol: in `m = 2.0 kg`, `m` is a symbol and
    `kg` a unit.
- **Bindings** (`scope.py`): `symbol → [Binding(value, number, unit, source, statement_id)]`.
  Sources:
  - `request`: the request text (read by the same front end, bound first);
  - `given`: a `Given:`, `Data:` or `Known:` statement;
  - `let`: `let`, `take`, `taking`, `using`, `with x = …`;
  - `result`: the final value of the answer's own chain;
  - `statement`: a bare value binding elsewhere in the answer (including a value the answer
    states for a constant);
  - `root`: a stated solution of an equation in the symbol (`x = 5 or x = −2` is no rebinding);
  - `substitution`: a value substituted into a symbol bound nowhere else. Such a binding only
    widens what a later substitution may match and is never a premise of its own check.

  A value after `at`, `when` or `if` in the answer (`At x = 1:`) is an evaluation point, not a
  binding. The front end never adds a constant value to scope; see D3 for the guarded booklet
  reading in checks. Rebinding adds a binding (ST-SCOPE-001 info when the value differs beyond
  rounding).
- **Binding scope** (`checks._scoped`; section 22, part scope). A binding holds in its own part
  from where it is stated. A check uses the bindings of its own part stated before it or in its
  own statements (`…, where x = 2`); another part's value only when its own part states none
  before it (a value carried forward from an earlier part); a value stated after it in its own
  part only when nothing else is in scope; never a later part's value. The request's values hold
  everywhere. A written substitution (R7) matches any value in that scope, because the written
  value shows which one was meant. An evaluation that writes no value for the symbol (the
  symbolic side under its bindings, an order between bound symbols, an equation's parameters)
  uses the value in force: the latest stated before it in its part (a whole root set when that is
  the latest). When the answer stated another value of the symbol earlier in the same part,
  which one was meant is a reading, so the failure of such a check is a warning (INT-SUBJ-004).
  So part (b) reusing part (a)'s letter for its own value is checked against that value, and a
  binding of one part never validates a calculation in another part that states its own.
- **Formulas.** A left-hand symbol or `f(x)` maps to an expression, recorded from definition
  and law links.

### 4.7 Relations (`relations.py`)

A chain `L0 op1 E1 … opk Ek` may continue across lines. Each link is classified by its two
endpoints: *value* (a single number or quantity), *closed* or *numeric* (no symbol, possibly with
units), *bound* (every symbol has a binding) or *symbolic* (a symbol with no binding). The
link's claim ids are the statements that hold its two endpoints. Every recognised relation ends
in one outcome: `check`, `binding`, `formula`, `context` or `undecided` (section 1).

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
| an equality with an application of an exponential model (the model's letter glued to its bracket) | `P(t + 1) = P₀e^(k(t + 1))` after `P = P₀e^(kt)` | `stem-mod` (section 21, item 5) |
| answer `Given:` binding against a request binding of the same symbol, or a request quantity of the same dimension | `Given: v = 20 m s⁻¹` | `stem-giv` |
| final value against a show-that target in the request | "Show that n ≈ 2.0 mol" | `stem-tgt` |
| chemical equation | `2H₂ + O₂ → 2H₂O` | `stem-chem` |
| Boolean equivalence | `¬(A ∧ B) = ¬A ∨ ¬B` | `stem-bool` |
| truth-table block | header `A B A∧B` | `stem-tt` |
| based numerals | `FF₁₆ = 255` | `stem-base` |
| a relation whose endpoints contain Unsupported | `f′(x) = 3x + 2` | ST-UNDEC-001 (reason) |
| a numeric relation whose operands include a symbol with no binding and no admissible booklet reading | `E = hf = 3.3e-19` with f unbound | ST-UNDEC-002 |

A stated root set is checked as a set: once `stem-sol` holds two or more roots of an equation
(`x² = 4 ⇒ x = −2 or x = 2`, or the same set over two lines), a step from that equation to one of
its members is context (`case`, naming the set), not a step checked on its own under the
principal-root condition, and no ST-ALG-001 is raised for it, since the other root is stated.
Every order and spelling of the set (`x = 2 or x = −2`, `x = ±2`) gets the same verdict
(section 22, S5).

A bare value binding with no relation stated (`The speed is 15 m/s.`, `m = 2.0 kg`) is a
binding, not a check. That keeps the existing Physics fixtures free of new findings. An order
chain is read (`T₁ = 300 K > T₂ = 250 K`), a factorisation inside a chain is checked as an
identity, a ratio equality `a:b = c:d` is compared by cross products, and a function or
derivative evaluated at a point is checked against the stated formula when one is recorded.
An evaluation of a function at a value (`f(2) = …`, and `N(15) = …` for a letter the text defines
as a function, `N(t) = …` or a model; section 21, item 5) is no step from the preceding line, and a
step over a function of an unknown is ST-UNDEC-001. Complex values are named undecided.

Check ids are planned here, deterministically, in document order: `stem-eq-1`, `stem-eq-2`,
… per kind. Parser and pack therefore agree on them. A planned check that `to_ir` cannot
encode keeps its id: the undecided finding names the id instead of a check being built.

### 4.8 Chemistry and Computer Science readings

- **Chemistry** (`chem.py`, chemistry, biology, ESS and the multi-science `stem` profiles):
  - Formulas with element symbols from the periodic-table symbol list (symbols only, no masses),
    counts (subscript or digit: `H₂O`, `H2O`, `H_2O`, `H_{2}O`), parenthesised or bracketed
    groups nested at most 3 deep, and hydrate dots (`CuSO₄·5H₂O`).
  - Charges `²⁺`, `⁻`, `^{2+}`, `^-`, and a glued ASCII charge at the end of a species
    (`Fe2+`, `SO42-`, `[Cu(NH3)4]2+`); electrons `e⁻`.
  - State symbols `(s) (l) (g) (aq)` are read and ignored.
  - Arrows `→`, `⇌`, `->`, `<=>`, `\rightarrow` and `\rightleftharpoons`; coefficients as
    integers, decimals or fractions (`½O₂`, `1/2 O2`).

  Isotope notation, an unknown element symbol and a bound exceeded give ST-CHEM-001. The module
  reads structure only; whether an equation balances is decided by the engine.
- **Computer Science** (`boolean.py`):
  - Boolean expressions with `∧ ∨ ¬ ⊕`, `AND OR NOT XOR`, `·`, `*` and `+` in Boolean context,
    and overbar or prime negation. Variables are single capital letters; a glued run of
    capitals (`AB`) is their AND. Precedence, lowest first: equivalence (`=`, `≡`, `⇔`), OR,
    XOR, AND, NOT. Boolean context: the profile is Computer Science and the span uses a Boolean
    operator, or every identifier is a single capital letter and every number is 0 or 1.
  - Truth tables of at most 5 inputs (32 rows), from a Markdown table or a plain block whose
    header names the inputs and one or more output expressions.
  - Based numerals (`FF₁₆`, `0xFF`, `0b1010`, `1010₂`; a hexadecimal numeral may open with a
    digit, `2A₁₆`).
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
| integer power | \|n\| ≤ 12; over a closed base with no unit, \|n\| ≤ 1000 (one value; beyond about 10^±300 it is not computed) | ST-UNDEC-001 |
| scientific exponent | \|e\| ≤ 99 | ST-LIM-001 |
| written digits per number | 30 | ST-LIM-001 |
| readings per expression / per check | 2 / 4 | ST-PARSE-002 |
| bindings per symbol | 8 | the oldest are dropped from matching; ST-SCOPE-001 info |
| symbols per check | 48 (the IR limit is 64) | ST-LIM-001 |
| interval operands per Form S check | 6 | ST-LIM-001 |
| STEM checks per report | 128 | ST-LIM-002 names the count and the first unchecked ids |
| math spans (and display rows) read per report | 1,024 | the rest stay text claims; ST-LIM-002 names how many were not read |
| statements (claims) | 512 (the report contract) | overflow merges into `s.tail` with the unresolved-issue text the bus turns into INT-REQ-013 |
| chemistry species per side; atoms per species; group nesting | 16; 999; 3 | ST-CHEM-001 |
| truth-table inputs | 5 | ST-UNDEC-001 |
| digits of a based numeral | 64 | not read as a based numeral (the scan stays bounded) |
| letters of one run segmented for implicit multiplication | 12 | the run is one unknown symbol |
| recorded formulas an algebra step includes | 8 | no further formula is added as a premise |
| digits of one IR literal after factoring | 40 (`scaling.MAX_LITERAL_DIGITS`) | ST-LIM-001 |
| IR bounds per check (checks stage) | 48 symbols, 128 premises, 2,000 nodes, depth 40, 32 n-ary arguments, polynomial degree 24 (`to_ir.IR_LIMITS`) | ST-LIM-001 |
| characters of a prose line the run finder scans in one pass | 20,000 | scanned in windows |
| document cache | 64 entries | LRU eviction |
| enclosure arguments | trig \|x\| ≤ 10⁹ rad, reduced modulo 2π; ln and log10 over [10⁻¹⁰⁰, 10¹⁰⁰]; exp over \|x\| ≤ 700; ≤ 400 series terms | ST-UNDEC-001 |

The front-end bounds are fields of `StemLimits` (`stem/limits.py`). The checks stage keeps its
IR bounds in `to_ir.IR_LIMITS` and `scaling.MAX_LITERAL_DIGITS`, and the enclosure routines
their argument bounds in `enclosures.py`.

---

## 5. Numbers, significant figures and tolerance

### 5.1 Exact numbers (`numbers.py`)

An `ExactNumber` holds:
- the exact `Fraction` value as written (scientific notation expanded exactly);
- the significant figures: leading zeros are not significant, trailing zeros after the point
  are, and scientific notation counts the mantissa;
- `last_place`, the power of ten of the last written digit;
- `half_width = ½·10^last_place`;
- `exact`: true when the written form has no decimal point anywhere (an integer, a vulgar
  fraction, a based numeral, an integer mantissa). This describes the written form only: a
  number that carries a unit is a measurement, and the checks never put it in exact mode
  (`200 km ÷ 3 h = 67 km h⁻¹` is measured data, fixture `stem-phys-030`);
- the decimal exponent, for scaling.

`scan_number` is the one number reader of the front end (the ledger's figure extraction uses
it too). It accepts only ASCII digits and checks the digit and exponent bounds before any
integer is built, so `10^999999` costs one linear scan and yields a named error.

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
- **R2 Relative slack τ.** The tolerance policy carries the task's and the answer's intent first,
  then the written form (section 22, S2):
  - **Stated exactness.** When the answer states exactness beside the relation ("Exactly 1/2 =
    0.51.", "= 0.51 exactly"), or the request states it ("Calculate 1/2 exactly, without
    rounding.", "the exact value", "do not round") for a relation between pure numbers, the
    comparison is exact: τ = 0 and h = 0 whatever the spelling of S, so `0.51` and `51/100` get
    the same verdict, a decimal root is the value it states, and written constants and carried
    values are taken as written. The request's intent is read per part (its own part's
    statements and those outside any part); a rounding instruction wins when a statement or the
    applicable statements ask for both ("the exact value, then to 3 s.f."). "Exactly" before a
    count ("exactly two reasons", "exactly 3 significant figures") or negated ("need not be
    exact") states no exactness. A quantity with a unit is a measurement: a request's
    exactness does not make it exact (the answer's own "exactly" still does).
  - **A rounding the request asks for** ("to 2 decimal places", "correct to 3 s.f."), or that the
    answer states beside the relation ("(to 2 d.p.)"), keeps the tolerance of the written digits,
    whatever the spelling of S: exact mode does not apply, an integer S has R1's half-width and a
    fraction of two written integers the half-width of its terminating decimal expansion (0 when
    it does not terminate). So under "to the nearest integer" `7/3 = 2` passes and `7/3 = 3` fails,
    and under "to 2 decimal places" `1/3 = 33/100` gets the verdict of `1/3 = 0.33`; with no rounding
    stated both `7/3 = 2` and `1/3 = 33/100` remain exact claims and fail.
  - `≈`, `≃` or `~`, or `=` after "approximately", "approx.", "about", "roughly", "estimate",
    "around" or "nearly": 1/20.
  - `=` with a measured operand: 1/100. Measured: a decimal point, scientific notation or a unit
    in the computed expression, or in a stated expression of rounded values
    (`ln 50 / ln 2 = 3.912/0.6931`); a stated value with a unit; a rounded intermediate or a
    written constant (R3). This covers constants written to fewer digits than were used (9.8
    against 9.81 is 0.1 %; 3.00 × 10⁸ against 2.998 × 10⁸ is 0.07 %). It stays well below the
    error classes this design must catch (a wrong formula, substitution, digit or power of ten,
    typically 5 % or more).
  - `=` over exact operands with a stated decimal: τ = 0. The decimal is read as rounded to its
    last digit (h alone), so its spelling never widens the band: `1/3 = 0.33` and `√2 = 1.41`
    pass, `1/2 = 0.51` and `5/3 = 1.6` fail, as `1/2 = 51/100` does.
  - **Exact mode** (every operand and S exact, `=`, and no rounding stated): τ = 0 and h = 0. So
    `7/3 = 2` fails.
  - **In an algebra step** a rounded value in the conclusion (a decimal, also after a leading `±`,
    as in `x² = 2 ⇒ x = ±1.41`) is compared within h of its last digit, with τ = 1/100 only when
    the step has a measured operand (in the preceding relation, the conclusion's other side, a
    binding or an included formula, or a constant or function): `2x = 1 ⇒ x = 0.51` fails as
    `x = 51/100` does, and `x² = 2 ⇒ x = ±1.42` fails.

  Each check records the policy that decided it and where it came from (the request, the
  answer's own words, the written form, or the check kind's fixed rule): `PlannedCheck.tolerance`,
  the description ("tolerance policy: …", carried to the receipt's formal check) and the
  problem's `notes`, which the signed result binds.
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
  When a single written value is set against another (a conversion, `72 km h⁻¹ = 20 m s⁻¹`),
  the left value's own half-width is added to the band.
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
- **R5 Conversions.** `2.5 km = 2500 m`, `72 km h⁻¹ = 20 m s⁻¹` and `25 °C = 298 K` use τ = 0
  (1/20 when the conversion is marked approximate; h = 0 when the answer states it is exact).
  The factors are exact, so the only slack is the half-widths of the two written values,
  `|C − S| ≤ h(S) + h(C)` in SI. Unknown unit atoms that are the same on both sides cancel;
  otherwise an unknown unit is checked as written only, at warning severity. A temperature on an
  offset scale follows section 6.1: `(20 + 5) °C = 298.15 K` is checked like `25 °C = 298.15 K`.
- **R6 Comparisons** (`<`, `≤`, `>`, `≥`, `≠`) between written values are exact, with no slack,
  as in quant's series checks.
- **R7 Substitution fidelity.** A substituted numeral w matches a binding b iff `|w − b| ≤
  max(h(b), h(w))`, in b's written unit or in SI: one value must be a rounding of the other. The
  two readings are a disjunction, so 2500 and 2.5 both match 2.5 km. τ = 0. In Mathematics an exact
  integer the answer states (`Let x = 3`) has h = 0. A value written in a unit of b's dimension that
  the same working uses (dm³ for a volume bound in cm³ when the concentration is in mol dm⁻³) also
  matches. (Section 24.6: until the argument diagnosis the bound was the sum h(b) + h(w), which let
  3 pass for 2.)
- **R8 Restated result.** A prose value S′ matches the chain's final value S iff `|S − S′| ≤
  max(h(S), h(S′))`, in SI, with τ = 0 (the sum before section 24.6).
- **R9 Prose relations** (per cent, fold, share and total) keep quant's `TOLERANCE_RULE`: 5 %
  and the 0.5-point floor. In SI reading the band is made sign-aware (section 12). Those
  statements are approximate by nature; equations are precise statements.
- **R10 Roots.** A stated decimal root r of a polynomial equation passes iff a real root lies
  in `[r − h(r), r + h(r)]` (Form S). An exact root passes iff it satisfies the equation exactly
  (linear substitution, D1).

**The observed case.** C = 5, S = 6.0, h = 0.05, τ = 1/100, and |5 − 6| = 1 > 0.05 + 0.05, so
the check fails. Under quant's 5 % rule it would have passed anything from 4.76 to 5.26.

**Short form** (`tolerance.SHORT_RULE`, the `[rule]` suffix of every description, 300
characters or fewer): "STEM tolerance: S must lie within h + τ·|C| of the value C computed
from the written expression; h is half a unit in S's last digit; τ is 1% for '=' over measured
data, 5% for '≈'/about, else 0; stated exactness makes h and τ 0; rounded values, constants and
functions range over intervals." The full rule is `tolerance.STEM_TOLERANCE_RULE`.

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
  example `m s⁻²`, `m/s/s`, `J mol⁻¹ K⁻¹`, `mol dm⁻³`, `kg·m/s`, `kJ mol⁻¹`. After a number, an
  exponent written in ASCII and glued to its atom is read too: a hyphen-minus or plus and one digit
  (`m s-1`, `mol dm-3`, `J kg-1 K-1`), one digit 2 to 9 after an atom of two or more letters (`cm3`,
  `mol2 dm-6`) or after a slash (`m/s2`, `kg/m3`); never more digits (`300 K-273`), a spaced sign, a
  sign followed by an atom of the same dimension (`5 m-3 m`), or a one-letter atom's digit right after
  the number (`2 m2`, `H2`), which keep their reading (section 21, item 6).
- **Factors.** SI conversion factors are exact `Fraction`s. Where no exact rational factor
  exists (the degree, which is π/180 rad, and the parsec) the factor is `None` and the unit still
  has a dimension. Inside a compound unit (`J kg⁻¹ °C⁻¹`) °C is a temperature interval, like K.
- **Offset scales (°C, °F)** (section 22, S1). Whether a temperature on an offset scale is a
  temperature (the offset 273.15 for °C, 459.67 for °F applied) or a difference is decided per
  relation, in every check that compares values (`eq`, `cnv`, `res`, `tgt`, `cmp`, `sub`,
  `giv`), never only in explicit conversions:
  - the relation's clause speaks of a change (a Δ-prefixed symbol, change, difference, rise,
    fall, ...): a difference, the factor alone;
  - every temperature of the relation is written on the same offset scale: compared on that
    scale, where an offset cancels (`20 °C + 5 °C = 25 °C`);
  - otherwise (set against kelvin or the other offset scale) a temperature, converted **once,
    on the value its side states**, never term by term (`Encoder._affine_point`): a value
    (`25 °C`, `−5 °C`), a unit written after a group (`(20 + 5) °C` is the evaluated `25 °C`,
    298.15 K, exactly as the literal is), or a symbol bound to such a temperature (its domain in
    kelvin). A side that combines such a temperature with other terms (`20 °C + 5 °C`,
    `2 × 10 °C`, `T₁ + 5 K`) cannot establish whether each term is a temperature or a
    difference: its SI reading is refused (ST-UNDEC-001 when no other reading remains; a
    failure of the remaining as-written reading is a warning, INT-SUBJ-004, so `25 °C + 273 =
    298 K` still passes as written and nothing is decided under a guess).
  A substituted temperature (R7) is in kelvin with the offset unless the symbol is Δ-prefixed; a
  Given temperature likewise unless the statement speaks of a change.
- **Not in the table.** `yr` (a known gap: ST-UNIT-001, see docs/STEM_RESULTS.md) and any unit
  not listed above.

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
| ms⁻¹ (a glued two-unit token with a negative exponent) | two readings: per millisecond (SI binding) and the writer's evident metre per second | — |

### 6.4 Readings: as written or SI

- Every quantity in the link carries a unit, or is a symbol bound with a unit: compare **in
  SI only**. So `2.0 km / 4.0 s = 0.5 m s⁻¹` fails, as it should, and symbols bound in different
  units are compared in SI (`m₁ = 500 g`, `m₂ = 1.0 kg`: `m₁ < m₂` holds; before the review fixes
  it was compared as written, 500 against 1.0).
- Some operands are bare numbers and some carry units: **disjunction {as written, SI}**. So
  `v = 72 km h⁻¹ ÷ 3.6 = 20 m s⁻¹` (3.6 is a bare factor) and `4.5/6.0 × 100 = 75 %` both pass.
- No operand carries a unit: compare as written, and S is read both as its number and in SI
  (`20 × 25 = 0.5 km` passes in SI).
- One exception: a lone power of ten with no unit (`10^(−8.2)`, `10^(−7)`) set against a value in a
  unit of concentration is the antilogarithm of a concentration scale, the concentration in mol dm⁻³
  (the unit pH, pOH, pKa and pKb are defined in), compared in SI only. Read as a bare number in SI it
  would match a stated value 10³ times too small, the factor an exponent 3 too small reproduces
  (section 21, item 1).
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

- Names map one-to-one into `^[a-z][a-z0-9_]{0,63}$` (`to_ir.ir_name`): v → `s_v`, V →
  `s_cap_v`, v₀ → `s_v_0` (the lexer names it `v_0`), Δv → `s_delta_v`, θ → `s_theta`, f′ →
  `s_f_prime`, with a numeric suffix on collision. Per-reading copies carry `_r2`, `_r3`.
- `Symbol.meaning` carries the original token and what it stands for.
- Auxiliaries are `q_<n>` (quotient), `p_<n>` (power base), `sq_<n>` (root), `enc_<n>`
  (enclosure), `x_<n>` (interval operands), `w_<n>` (substituted values), `root_<n>`, `k_<n>`,
  `t_<el>_<l|r>` (balance tallies), `o_<row>_<col>` (truth-table outputs), and `c`, `r`, `l`
  (the compared values). User symbols always start with `s_`, so they never collide with these.

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
| `a / b`, b closed but compound | auxiliary q: `Q_DEF q·b = a`, `GUARD b ≠ 0`. Precheck: b exactly 0 gives ST-UNDEF-001 and no check; a closed b whose admissible values include 0 gives ST-UNDEC-001 | linear |
| `a / b`, b contains symbols | `Q_DEF q·b = a`, `GUARD b ≠ 0` (grounded `assumption`). Never a `div` by a variable (E202) | nonlinear |
| `xⁿ`, 2 ≤ n ≤ 12 | `mul` of n copies; a compound base first gets `p = x` | linear if x is closed |
| `x¹`, `x⁰` | x; `1` with `GUARD x ≠ 0` (0⁰ gives ST-UNDEF-001) | — |
| `xⁿ`, n < 0 | `q·x^|n| = 1`, `GUARD x ≠ 0` | linear if x is closed |
| `√x`, `x^½` | `sq ≥ 0`, `sq·sq = x`. Precheck: a closed negative x gives ST-UNDEF-001 | nonlinear |
| `bⁿ`, b closed with no unit, n an integer beyond 12 and up to 1000 (`RealPower`) | its exact value when it fits one literal (`2^{20} = 1048576`; a negative base takes the sign of n's parity); otherwise the outward-rounded interval power of b (`Interval.power`, cross-checked against `math.pow`), which forces Form S; a value beyond about 10^±300 is ST-UNDEC-001 and a zero base under a power that is not positive ST-UNDEF-001; an algebra step that holds the enclosed form is ST-UNDEC-001 | linear |
| `b^x`, b and x closed with no unit, x no integer (`RealPower`) | its exact value when it is rational (`16^(3/4) = 8`: b's numerator and denominator are exact q-th powers for x = p/q); otherwise an enclosure symbol `enc` of `exp(x·ln b)` for b > 0 (grounded `arithmetic_fact`, cross-checked against `math.pow`), which forces Form S, and an algebra step that holds one is ST-UNDEC-001. `0^x` with x > 0 is 0; a base that is zero under an exponent that is not positive gives ST-UNDEF-001, one that is or may be negative ST-UNDEC-001 (no real power is chosen) | linear |
| `B^X`, B e (mathematics and Computer Science readings) or a positive rational, X a polynomial in symbols with rational coefficients, in a model evaluation only (`stem-mod`) | with X = c + Σ qᵢ·mᵢ: the closed factor B^c (exact or enclosed) times Π uᵢ^(qᵢ/sᵢ), one positive variable uᵢ = B^(sᵢ·mᵢ) per base and monomial (`U_POS uᵢ > 0`, or `U_LO`/`U_HI` the enclosure of B^(sᵢ·range) when every symbol of mᵢ has stated values; grounded `arithmetic_fact`). A relaxation: every real solution gives such uᵢ, so only UNSATISFIABLE decides; Form S | nonlinear |
| `\|x\|` | `ite(x ≥ 0, x, −x)` | linear |
| `n %` | n/100 (SI reading); n (as written) | linear |
| `±`, `∓` inside a formula | the sign of the reading: `eq` and `sub` require both choices (AND); a step's relations take either (OR); roots expand to two | as the operands |
| `value ± uncertainty` | an interval binding | — |
| ratio `a:b = c:d` | `a·d = b·c` over closed terms | linear |
| exact-table function | the exact value (rational, or a surd through `sq` of 2 or 3): sin, cos and tan of multiples of 30° and 45° (and the same angles as rational multiples of π), log₁₀ and log_b of exact powers, ln 1, exp 0, inverse functions at table values | as the surd |
| other sin, cos, tan, arcsin, arccos, arctan, ln, log10, exp of a closed argument; π; e | enclosure symbol `enc` with `ENC_LO ≤ enc ≤ ENC_HI` (grounded `arithmetic_fact`, note "enclosure computed by the STEM pack; the engine decides the stated relation over every admissible value"); forces Form S | linear |
| a function of a non-closed argument | ST-UNDEC-001 ("function of an unknown") | — |
| Boolean `∧ · AND`, `∨ + OR`, `¬ ′ overbar NOT`, `⊕ XOR` | `and`, `or`, `not`, `not(iff)` | — |
| based numeral | `IntConst` of its value | — |

### 7.5 Enclosures (`enclosures.py`)

- **Method.** Interval arithmetic over exact `Fraction` endpoints, every operation rounded
  outward to 192 significant bits, so the true value always stays inside. Series with explicit
  remainder bounds: Machin's formula for π, the exponential series after halving the argument,
  the inverse-hyperbolic-tangent series for the logarithm after reduction by powers of two,
  Taylor series for sine and cosine after reduction modulo 2π, and Euler's accelerated series
  for the arctangent. The result is `[lo, hi]` with `hi − lo ≤ 10⁻¹⁵·max(1, |mid|)`; bounds are
  written with 25 significant digits.
- **Cross-check.** The routine checks `lo ≤ libm(x) ≤ hi`, within 10⁻⁹ relative, using the
  standard `math` module. A mismatch gives ST-INTERNAL-001 and no check. `math` is used for
  nothing else.
- **Bounds.** Iterations and argument ranges are bounded (section 4.9). Outside a function's
  domain (the logarithm of a non-positive value, arcsin of 1.5, the tangent at a pole) the
  relation is ST-UNDEF-001; beyond an argument bound it is ST-UNDEC-001.
- **Angles.** An argument written with `°` is in degrees; an argument holding π is in radians;
  otherwise the angle is ambiguous and two readings are built, degrees and radians. The result
  of an inverse function is likewise read in both units.

### 7.6 Grounding of premises (provenance the engine reports, never judges)

| Premise | Grounding |
| --- | --- |
| a value located in the request text | `task_setting`, `verified=True` (located deterministically) |
| the report's own figures, `C_DEF`, `R`, `W`, `L_DEF`/`R_DEF` of compared values, and a carried intermediate's rounding interval | `supplied_text`, `verified=True`, note "figure stated in the report itself" (quant's convention) |
| a stated law (`FORMULA`), or the preceding relation used as an algebra premise (`PREV`) | `specialist_inference` |
| guards (`GUARD_*`) and step side conditions (`SIDE_ROOT`, the principal root) | `assumption` |
| auxiliary definitions (`Q_DEF`, `S_SQ`, `P_DEF`), tallies, enclosures (`ENC_*`) and a written constant widened to its booklet value (D3a) | `arithmetic_fact`, note "encoding device: defines the auxiliary as the written expression; not a claim of the report" (enclosures: "enclosure computed by the STEM pack; the engine decides the stated relation over every admissible value") |
| a booklet value for an unstated symbol (D3b) | `assumption`, with a note that the STEM pack supplied it and the report did not state it |

The engine then lists laws, guards, side conditions and supplied constants in
`ungrounded_dependencies`. A passing check therefore never hides what it relied on.
Since engine 0.4.0 (policy 2026.10-v4) a premise of a task or source kind that no check in
this process verified is an unverified dependency whatever its kind, so the encoding devices
grounded `arithmetic_fact` above are listed in `unverified_dependencies` of the STEM results that
rely on them. No STEM decision reads the dependency lists: a STEM check's finding rests on the
engine status of its own encoding, under the tolerance rule.

### 7.7 Problem fields

- `problem_id`: `stem-<kind>-<report>-<n>`, at most 128 characters; a long one is cut and
  given a 12-character sha256 suffix.
- `claim_id`: `<report_id>:<first statement id>`, bounded the same way.
- `query`: `entailment` (Form E, truth tables), or `satisfiability` (Form S, Boolean
  identities).
- `notes` (at most 4,000 characters): the scope statement `STEM_SCOPE` first; "policy:
  nonlinear" when used; "decimal exponent factored: 10^F" when a frame other than 0 is used;
  the readings in force.

`notes` is part of the problem digest, so the binding covers them.

### 7.8 What is never encoded

- Truth of a law or a datum.
- Unit correctness beyond section 6.5 and the explicit conversion checks.
- Calculus: derivatives, integrals, limits, series.
- Σ with symbolic bounds.
- Vectors, matrices and complex numbers.
- Factorials and combinatorics with `!`.
- Symbolic powers, non-integer powers of anything but a closed value with no unit (a closed one is
  decided exactly when its value is rational, else through an enclosure, section 21), and integer
  powers beyond 12 of anything but a closed value with no unit. A power of e or of a positive rational
  with an exponent in symbols is read only inside a model evaluation (`stem-mod`, section 21, item 5),
  through positive variables that can refute a link but never prove it for every value.
- A function of an unknown (an exponential model applied to an argument is the one reading, `stem-mod`;
  no algebra step is read over an application of a letter the text defines as a function, section 21,
  item 5).
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
| `stem-sub-N` (`stem_substitution`) | substituted numerals against the symbols' bindings (R7). When the symbolic and numeric sides have the same tree shape, each aligned symbol is checked (a value written in another order of the same product or sum also matches, by bounded injective matching); otherwise, if every symbol is bound, the symbolic side under its bindings is checked against the numeric side (Form S over the binding intervals). A symbol with no binding takes a D3b booklet reading admitted by a dimension check, or the relation is ST-UNDEC-002 | E (pairs); E or S (evaluation) | as needed | error; warning when a D3b booklet value was used or a unit was unknown |
| `stem-alg-N` (`stem_algebra`) | the next relation follows from the preceding one, plus scope bindings of the symbols involved, plus at most 8 recorded formulas mentioning them, plus side conditions: divisors ≠ 0; a principal (non-negative) root in sciences profiles; a rounded value in the conclusion within its band (R2, R4) | E: ENTAILED | nonlinear when needed | error when the step is a pure manipulation (its symbols are a subset of the premise's symbols, bound symbols and included formulas); warning when it brings in unrelated symbols (an unstated law may be at work) |
| `stem-sol-N` (`stem_solution`) | membership: each stated root satisfies the equation (exact: linear substitution; decimal: R10). Completeness: the equation entails the disjunction of the stated roots, built only when the statement claims the full set (section 24.11, solution sets), the parameters are exact and neither the statement nor the request restricts the domain ("positive", "x > 0", "length", "time", "reject", ...). A root may also be a decimal the answer states in prose for the quantity it named by the symbol ("Let $M$ be the monthly payment" … "Her monthly payment is €352.19"; section 21, item 4): membership only, over its rounding interval widened by τ = 1/100 | E; S for decimal roots | as needed (membership of an exact root is linear; completeness is nonlinear) | error |
| `stem-mod-N` (`stem_model`) | an equality with an application of an exponential model, the model's expression at the written argument against the other side: some value of the variables (the model's variable, every symbol with no stated value) and of the stated symbols within their stated values satisfies it, every power of an exponent in symbols read through positive variables (section 21, item 5) | S: SATISFIABLE (UNSATISFIABLE: no value satisfies the link) | nonlinear | error |
| `stem-cnv-N` (`stem_conversion`) | an explicit unit conversion (R5) | E | linear | error; warning when a unit was unknown |
| `stem-cmp-N` (`stem_comparison`) | a stated order or inequality between values (R6); bound symbols with several values pass when some admissible values satisfy it; also inequality-solving steps, checked as `alg` | E (or S) | as needed | error |
| `stem-res-N` (`stem_result`) | a prose restatement against the chain's final value (R8) | E | linear | error; warning when a unit was unknown |
| `stem-giv-N` (`stem_given`) | an answer's `Given:` value against the request's binding of that symbol, or a request quantity of the same dimension | E | linear | warning (symbol identity across texts is a reading) |
| `stem-tgt-N` (`stem_target`) | the final value of a show-that answer against the request's target | E | linear | warning |
| `stem-chem-N` (`stem_balance`) | element and charge balance. Coefficients are pinned; tally symbols `t_<el>_l` and `t_<el>_r` are defined per element; the conclusion is a conjunction of equalities, so the counterexample model shows the unbalanced tallies | E (Int, or Real for fractional coefficients) | linear | error |
| `stem-bool-N` (`stem_boolean`) | Boolean identity: premise `NEG: ¬(lhs ⇔ rhs)` | satisfiability, expected UNSATISFIABLE; SATISFIABLE is a failure whose witness is a distinguishing assignment | linear | error |
| `stem-tt-N` (`stem_truth_table`) | every row's stated output: stated outputs are pinned Bool symbols; the conclusion is the conjunction over rows of `o_r ⇔ expr(row inputs)` | E | linear | error |
| `stem-base-N` (`stem_base`) | a base conversion as exact Int arithmetic | E | linear | error |

The policy is read from the built IR (`to_ir.inspect_ir`): `nonlinear` exactly when a `mul` has
two factors that hold variables (the validator's rule; the tests compare it with
`engine.policies.required_policy`). The column says when that happens. A check whose encoding
would exceed polynomial degree 24 is not built (ST-LIM-001).

Each description has the form `<what was checked>: '<statement, ≤ 160 chars>' [claims s2.3,
s2.4] [<short rule>] <form; policy; tolerance policy; readings; details>`, at most 1,200
characters. Descriptions name the tolerance policy that decided the check and where it came from
(section 5.2, R2; also `PlannedCheck.tolerance` and the problem's `notes`), readings, factored
exponents, supplied constants and side conditions. `StemPack` rewrites the statement ids in a
description to the report's own claim ids.

Withheld relations. The checks stage decides only relations whose two sides are whole, so a
misreading by the front end can never become an error. A relation is withheld (ST-PARSE-001,
warning, the check id named) when an arithmetic operator adjoins one of its operands in the text
(`xy + y = …` read as `+ y = …`), when an operand opens with a sign right after a symbol-like
token or a stray character, or when prose stands between the two sides of one link. These
guards only ever withhold a check; none decides one (`stem/ENCODINGS.md`).

### 8.2 Finding codes

The column "Decided by" means:
- **engine**: a signed Z3 result;
- **deterministic**: rule-based reading;
- **numeric**: exact `Fraction` precheck or bookkeeping.

The STEM pack itself emits **no error-severity structural finding**. Every STEM error comes
from an engine result.

| Code | Severity | Decided by | Meaning |
| --- | --- | --- | --- |
| INT-SUBJ-001 | error | engine | a check of the report's own STEM statement does not hold, and it rested only on what the report or request states plus exact encoding devices (existing code; now carries `claim_ids`; for a STEM check the message gives the counterexample's computed value `c` and stated value `r`) |
| INT-SUBJ-002 | warning | engine | such a check is undecided: UNKNOWN, TIMEOUT, UNSUPPORTED, INVALID_FORMALIZATION, INTERNAL_ERROR, a vacuous result (E108), or INCONSISTENT_PREMISES on a check with `inconsistent_is_failure=False`; also (deterministic) an unknown policy name, an exception while deciding the check, or the report's STEM check budget (8 s) spent (existing code; now carries `claim_ids`) |
| INT-SUBJ-003 | error | deterministic | an error-severity pack finding, escalated (existing; STEM never produces one) |
| INT-SUBJ-004 | warning | engine | NEW: a check that relied on a reading the report did not state does not hold: a booklet value for an unstated symbol, symbol identity across request and answer, a show-that target, a step bringing in unrelated symbols, an unknown unit, the value in force of a symbol the answer rebinds in the same part, or a relation whose SI reading is refused because a temperature on an offset scale is combined with other terms |
| BR-INTERNAL-001 | warning | deterministic | NEW (`SubjectBranch.run_packs`): pack `<name>` failed internally (`<type>`) during `<checks or formal checks>`; its findings are missing from this receipt, and the router must not treat the pack as passed |
| ST-PARSE-001 | warning | deterministic | a math span uses notation outside the grammar (named: unknown LaTeX command, unbalanced group, a symbolic power); its relations are not checked |
| ST-PARSE-002 | warning | deterministic | an expression has more than 2 readings (or a check more than 4): implicit multiplication or unit/symbol ambiguity; not checked |
| ST-UNDEC-001 | warning | deterministic | a recognised relation outside the encodings (calculus, limits, Σ, vectors, matrices, complex numbers, `!`, asymptotic notation, a function of an unknown, an approximation step such as sin θ ≈ θ, an angle range, a temperature on an offset scale combined with other terms against another scale); the reason is named |
| ST-UNDEC-002 | warning | deterministic | a numeric relation depends on a symbol with no stated value and no admissible booklet reading |
| ST-UNDEF-001 | warning | numeric | a written expression is undefined (division by an exact zero, an even root of a negative value, the logarithm of a non-positive value, 0⁰, tan at a pole, arcsin or arccos outside [−1, 1]); no check is built |
| ST-UNIT-001 | warning | deterministic | a unit expression is not recognised; the relation is checked as written only, at warning severity |
| ST-UNIT-002 | info | deterministic | an ambiguous unit symbol (M: molar or mega) is checked under both readings |
| ST-DIM-001 | warning | deterministic | the two sides of a stated relation have different dimensions (units read unambiguously) |
| ST-DIM-002 | warning | deterministic | a sum or difference of terms with different dimensions |
| ST-ALG-001 | warning | deterministic | a mathematics step takes only the non-negative square root, and no domain restriction is stated (the algebra is still checked under that side condition) |
| ST-CHEM-001 | warning | deterministic | a chemical equation cannot be read (unknown element symbol, isotope notation, a bound exceeded); its balance is not checked |
| ST-CODE-001 | info | deterministic | a code block is present; it was not executed and not checked |
| ST-SCOPE-001 | info | deterministic | a symbol is rebound to a different value inside the answer; a calculation is checked against the values in force in its own part, stated before it (section 4.6) |
| ST-LIM-001 | warning | numeric | an expression or literal exceeds a front-end or IR bound (span, links, nodes, depth, exponent, digits after factoring, symbols, intervals); not checked |
| ST-LIM-002 | warning | deterministic | more relations than the per-report check cap (128), or more math spans than the per-report reading cap (1,024); the count and the first unchecked ids or statements are named |
| ST-INTERNAL-001 | warning | deterministic | the STEM pack failed internally while building checks, an enclosure failed its cross-check against `math`, or a built problem was refused by `Problem.model_validate`; the affected checks are missing and must not be read as passed |
| ST-CLAIM-001 | warning | deterministic | NEW (STEM review S4, section 23.2): a claim id of the report is spelled like a statement id of the STEM reading (`s1.1`, `m1.1`) but its text is another statement's; the statement's checks and findings are attached by text to the claims that hold it, never by the id, and the finding names both |
| INT-HIST-001 | the carried finding's | deterministic | NEW (relay history, section 11.6): an unresolved finding of an earlier delivered transmission that a relay, forward or synthesis builds on, carried with its own severity, claims and signed result; never blocking |
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

- **Claims.** Claims come from `StemDocument` statements: a sentence, a derivation line, a
  display row, a list item, a code block, a table or a data line. Ids are
  `s<paragraph>.<statement>` in the `sciences` branch and the same numbering with the branch's
  own letter in the other two (`m1.2` in `mathematics`, `c1.2` in `computer_science`), so a
  Physics and a Mathematics report on one task never share a claim id (the combinator's ledger
  refuses shared ids, INT-LEDGER-014). Ids are stable and deterministic. `StemTextParser` takes
  `agent_id` and `mode`, declares `accepts_request_text`, and the channel passes it the
  request text, so the parser and the pack read the same document.
- **Overflow.** Claims beyond 512 merge into `s.tail` (`m.tail`, `c.tail`) with the
  unresolved-issue text the bus turns into INT-REQ-013, as in the generic parser.
- **Empty text** still raises `AdapterError` (`tests/channel/test_channel_robustness.py:57`).
  A code-only answer yields claims; it does not raise.
- **Markup.** `markdown.strip_markup` is not applied wholesale, because it drops code fences
  and some bracket lines. Headings become part labels. Emphasis is dropped only in the prose
  view. Code blocks, tables and data lines are kept.
- **Notes.** Notes and self-certification use the shared `is_note_sentence` and
  `is_self_certification` (role `other`). A statement that carries maths is never taken for a
  note because it has no words (`√8 = 2√2`).
- **Quotations** of supplied texts and peer reports are found and credited by the rule every
  parser shares (`sources.attribute_excerpt`), on the quotation view of the answer (code masked;
  an inch or arcsecond mark after a number is not a quotation mark).
- **Assumptions.** A claim whose numeric relations the pack decides carries the assumption
  "numeric relations of this statement are decided by the STEM pack checks <ids>". The ids
  are planned in the shared document.
- **Structured reports.** For a report that arrives structured (JSON), `StemPack` maps
  statements to the report's own claims by offset when the claim texts are offset substrings,
  else by the shared two-way substring rule (`_claims_mentioning`), on the statement as written
  and as this parser gives it (`statement_claim_text`: interior markup left out). Claim ids never
  outrank source spans (STEM review S4): a claim whose id is the statement's (`s1.2`, `m1.2`) is
  its one claim only when its text agrees with the statement; otherwise the statement goes to the
  claims holding its text and ST-CLAIM-001 names the disagreement (section 23.2).

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
| A heading line with no content of its own ("Given:", "Working:") | structural | unknown | supporting | NOT_ELIGIBLE_OTHER (no numerals) |

Every chain-bearing part yields a material result, so INT-REQ-012 ("no answer") never fires
on a derivation.

Since the merge with the round-7 development branch, roles, materiality and supports are the
generic branch's round-7 reading, with the refinements of this table applied only where round 7
did not rule (section 20.2): a link supports the point and rests on nothing, and a consequence
rests on the claims before it.

### 9.3 Eligibility (`translate/eligibility.py`)

Rule 4 (COUNT_ROLES) also accepts a text with a mathematical relation sign between operands
(`=`, `≠`, `<`, `>`, `≤`, `≥`, `≈`). In the same profiles `has_numeral(text, scripts=True)`
also counts superscript and subscript digits (`x²`, `v₀`). Both apply only when the profile
allows QUANTITATIVE_CLAIM, so argument-only profiles are unchanged. POLICY_VERSION is bumped.
Eligibility classes for the sciences, mathematics and CS profiles remain `_QUANTITATIVE`.

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
   - cs, comp sci, computer sci, software engineering (and the existing computer science,
     computing) → computer_science.
   - environmental science, environmental systems → ess.
   - statistics, stats → mathematics_ai.
   - maths: aa, math: aa, mathematics: aa, aa hl, aa sl → mathematics_aa, and the AI
     equivalents (maths: ai, math: ai, mathematics: ai, ai hl, ai sl) → mathematics_ai.
   - further mathematics, further maths → mathematics_aa (working configuration, recorded as
     such).
3. **A new profile `stem`** ("General Science (STEM)", group sciences, `_QUANTITATIVE`, Int
   and Real). It covers "science", "sciences", "general science", "stem" and "engineering". It
   also covers labels that name two or more different sciences ("Physics/Chemistry"): when
   matches fall in two or more of the six science profiles and the longest match is one of
   them, the label resolves to `stem` rather than the longest.
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

   This is `subjects.STEM_ENCODING_GUIDANCE`, added for every key of `STEM_PROFILE_KEYS`. It
   bumps TRANSLATOR_VERSION. The pinned prompt version `translate_v1` and its file are
   unchanged.

### 10.2 `branches/registry.py`

`CORE_SI = CorePack(reading=SI_READING)`. Its `name` is still `"core"` and it comes first in
every STEM branch (`tests/branches/test_quant_and_packs.py:77-79`).

| Branch key | Profile keys | Parser | Packs |
| --- | --- | --- | --- |
| `sciences` | physics, chemistry, biology, ess, sports_science, design_technology, stem | `StemTextParser(agent_id="science-specialist", mode="sciences")` | (CORE_SI, StemPack("sciences")) |
| `mathematics` | mathematics_aa, mathematics_ai, mathematics | `StemTextParser(agent_id="maths-specialist", mode="mathematics")` | (CORE_SI, StemPack("mathematics")) |
| `computer_science` | computer_science | `StemTextParser(agent_id="cs-specialist", mode="computer_science")` | (CORE_SI, StemPack("computer_science")) |

`generic` stays the default for `unknown`. The reading profile follows the report's subject
(`stem_profile_key`): its own profile when that is a STEM profile, else the branch mode's
fallback (`stem`, `mathematics` or `computer_science`). The per-profile switches are in
`stem.limits.PROFILES`: chemical equations for chemistry, biology, ESS and `stem`; a bare `M`
after a number is molar in chemistry and biology, molar or mega in physics and `stem`, mega
elsewhere; the tonne in ESS and Design Technology; Boolean words and indented code blocks in
Computer Science; only the principal root in the sciences. Each STEM branch sets
`hub_hooks=STEM_HOOKS` (section 11).

**Recorded behaviour change.** Two existing assertions encoded the pre-STEM routing:
- `tests/branches/test_hub.py:46`: `branch_for("Chemistry") == "generic"`;
- `tests/branches/test_quant_and_packs.py:76`: `for_subject("Physics")[0].key == "generic"`.

The user's goal and the observed defect are exactly this routing, so it must change. Stage
`branch` replaced each with an assertion of equal strength for the new branch (`"sciences"`)
and added an unknown → generic assertion beside it (`"Underwater Basket Weaving"`). Nothing was
deleted; each changed line carries a comment naming this section. The change is recorded for
the overseer audit and the user's sign-off, which happen in the integrated arena. Every other
existing test that runs a Physics plan passes unchanged. In particular `StemPack` emits nothing
on `The speed is 15 m/s.` (no relation is stated) and only info for unchecked code.

---

## 11. Hub, channel and receipts

### 11.1 `branches/base.py`

- `FormalCheck` gains the four fields of section 8.1.
- `SubjectBranch` gains `hub_hooks: Optional[BranchHooks] = None`.
- `SubjectBranch.run_packs` guards each pack call (its `checks` and its formal checks
  separately). On an exception it adds BR-INTERNAL-001 (warning: the pack, the exception type
  and the stage, never the exception's text) and continues with the next pack.
- It prefers `pack.formal_checks_for(report, request_text)` when the pack defines it.
- On relay (`req=None`, so `request_text=None`) STEM checks bind only to the answer's own
  values, and `stem-giv` and `stem-tgt` are not built (`StemPack.formal_checks` is this relay
  form).
- `BranchHooks` is a protocol of plain-data methods, each given the subject profile key the
  channel resolved for the agent: `request_imperatives` (a tuple), `coverage_terms(claim_text,
  report_text, request_text, profile_key)`, `echo_exempt(report_text, request_text,
  profile_key)` and `word_count_view(text, profile_key)`.

### 11.2 `channel/bus.py`

`_branch_checks`:
- calls `verify(fc.problem, policy_config(fc.policy, cfg), limits=policy_limits(fc.policy),
  signing_key, key_id)`, where `cfg` is the channel config. For the `linear` policy that is
  `cfg` itself; for `nonlinear` it is `cfg` with `rlimit` at most `NONLINEAR_RLIMIT` (a
  caller's lower `rlimit` is kept), so cutoffs are deterministic. An unknown policy name gives
  INT-SUBJ-002 "unknown policy"; it is never run under some other policy.
- runs the STEM checks of one report (kinds `stem_*`) under a wall-clock budget
  (`STEM_CHECK_BUDGET_S`, 8 s): checks left when it is spent are not run and are INT-SUBJ-002
  ("check budget"), never success. Other packs' checks are not budgeted.
- maps the status as follows:
  - `satisfied = True` iff the status equals `expected_if_sound` and no E108 diagnostic is
    present;
  - `satisfied = False` iff the status is definitive and not the expected one, except
    INCONSISTENT_PREMISES when `inconsistent_is_failure` is False;
  - `None` otherwise.

  Before this change the False list missed SATISFIABLE for checks expecting UNSATISFIABLE, and
  an ENTAILED result carrying E108 showed as satisfied. Existing ENTAILED-expecting checks with
  non-vacuous proofs keep their behaviour.
- maps `False` with `failure_severity="error"` to INT-SUBJ-001, `False` with `"warning"` to
  INT-SUBJ-004, and `None` to INT-SUBJ-002. Each carries `claim_ids=list(fc.claim_ids)`. For a
  STEM check with a counterexample, the message adds the model's `c` (the value computed from
  the written expression) and `r` (the stated value).
- truncates `ConstraintResult.detail` and finding messages with `translate.common.truncate`
  (2000 each), so a long description can never raise out of `hub.receive`. Each verify call
  and result construction is guarded: an exception becomes INT-SUBJ-002 "internal" for that
  check alone.
- **Degrades safely.** If the policy pass-through were missing, nonlinear checks would come
  back UNSUPPORTED (E201) and show as undecided, never as success.

Hooks (`stem/hub_hooks.py`, `STEM_HOOKS`; none for other branches, so their behaviour is
unchanged). The channel calls each through a guard: a hook that fails falls back to the
channel's own reading, because a hook only ever refines a heuristic.
- `coverage_terms`, read by `_coverage`: quantity names keyed by the dimensions of the claim's
  quantities (m s⁻² → acceleration; N → force, weight, tension; J → energy, work; …) and of the
  bound symbols it uses, the names of their units (mm → millimetre, metre; % → percentage), what
  its relations produce (stated roots → root, solution; an order relation → inequality; a
  chemical equation → equation, reaction; a truth table → truth, table; a base conversion →
  binary, denary, hexadecimal; a Boolean identity → Boolean, expression), a derivative written in
  the claim (f′(2), dy/dx → gradient, derivative) and a component's direction (`F_x` →
  horizontal component). A claim that holds a planned computation (an engine check of its
  arithmetic, substitution, conversion, algebra, roots, balance, Boolean identity or based
  numeral) also offers the computing command words (calculate, determine, find, convert,
  solve, evaluate, …): it does compute. Since the STEM review (S3, section 23.1) the channel never
  counts a command word as evidence on its own for an item that names what it wants: the shared
  terms must include one of the item's topic terms (`bus._COMMAND_STEMS` lists the command and form
  words), or `topic_evidence` must hold, so "2 + 2 = 4" addresses no "Calculate the acceleration"
  while an equation-only correct answer still addresses its item. An item whose words are all
  command words but which names what it asks for in notation (`names_notation`: "Solve 3x + 5 =
  20", "Simplify √50", "Find u₆ and S₅", "Calculate v if d = 120 m and t = 8 s") is addressed only by
  a claim `topic_evidence` finds about that notation; an item that names neither ("Find the final
  value") keeps the plain lexical reading. The method stays `lexical_heuristic`.
- `topic_evidence(item_text, claim_text, report_text, request_text, profile_key, notation_only=False)`,
  an optional hook read through `getattr` (the `BranchHooks` protocol is unchanged): a computing claim
  is about an item when it gives a value to a symbol the item asks for, or computes with enough of
  the item's own figures, unless the units it states name another quantity than any the item names
  in words (`s = ½ × 20 × 4.0 = 40 m` computes a distance from the data of "the acceleration from
  20 m/s in 4.0 s" and does not answer it). A line that computes nothing is never evidence.
  - The symbols an item asks for (normalised as the front end names them): a subscripted name
    ("Find S₁₀" and `S_{10} = 210`), a symbol right after a command word ("Calculate v if …", "Find
    the value of k", "Calculate Kc" for `K_c`), a show-that target ("Show that its gradient is m = 1"
    and `m = …`, read after "show that") and, for an item that asks to solve an equation or names
    nothing in words, the unknowns of its equations ("Solve 3x + 5 = 20" and `x = 5`). A symbol the
    item gives a value for ("if d = 120 m and t = 8 s", "Given that t = 8 s, show that …") is an
    input and never evidence: `t = 2 + 2 = 4` answers neither item. The symbols of a formula the
    item quotes ("using v = u + at") are not asked either.
  - The figures: the item's numerals (superscripts read as figures of their own, so `2³ × 2⁴`
    writes 2, 3 and 4; its opening label, mark annotations such as "[2 marks]" and precision
    instructions such as "to 3 significant figures" are no figures) shared with the claim must weigh
    three, where a single-digit whole number weighs one and any other figure two (the gradient
    through (1, 3) and (5, 7) and `m = (7 − 3)/(5 − 1) = 1` share four), or the item's only figure
    must be shared and be no single-digit whole number ("Simplify √50"). Two shared single digits are
    no evidence: `2 + 2 = 4` addresses no "acceleration of a trolley that reaches 4 m/s in 2 s", and
    `4 − 2 = 2` no "force on a 2 kg mass accelerating at 4 m/s²".
  - `notation_only` (an item that names nothing in words): the unknowns of its equations count, and
    the claim's units are set against no word of it ("Calculate v if d = 120 m and t = 8 s" asks for
    a speed and writes a length and a time).
- `names_notation(item_text, profile_key)`, optional likewise: the item writes what it asks for in
  maths (a figure that is no label, mark or precision instruction, or a symbol). A failing or absent
  hook leaves the item to the plain reading.
- `echo_exempt`, read by `_request_echo`: a STEM answer containing at least one planned
  computation link (`stem-eq`, `stem-alg` or `stem-sol`) that is absent from the request is
  never INT-REQ-011. This fixes the false error on the correct show-that answer
  `n = m/M = 36 g / 18 g mol⁻¹ = 2.0 mol`.
- `request_imperatives` (`STEM_IMPERATIVES`), passed to `extract_items(text,
  extra_imperatives=…)`: determine, deduce, derive, state, find, solve, sketch, estimate,
  predict, verify, show, at the start of a sentence or after a part label. Multi-part STEM
  questions then become one item per part.
- `word_count_view`, read by `count_answer_words`: LaTeX control words are not words, and each
  math span and each code block counts as one word. This avoids a false INT-REQ-005.

### 11.3 `channel/request_parser.py`

`extract_items(text, *, extra_imperatives=())` and `count_answer_words(text, *, view=None)`.
With extra imperatives, a request line that opens with a part label (`(a)`, `b)`, `(ii)`,
`Part (c)`) also starts a new sentence. The defaults reproduce the general reading exactly.

### 11.4 Receipts

Receipts keep their shape, with one additive field since the STEM review:
- `formal_checks` holds `ConstraintResult(constraint_id=check_id, method="formal",
  formal_result_id, formal_status)`;
- `structural_findings` holds the ST findings;
- `history` (default empty) references the earlier receipts a relay, forward or synthesis builds
  on (`ReceiptReference`: receipt and message ids, direction, status, payload, and what each left
  unresolved), section 11.6;
- the summary keeps counts "N (ok, FAILED, undecided)", names at most 8 FAILED and 8
  undecided ids, shows the code histogram (ST-* included), says how many earlier receipts the
  transmission carries and how many left findings unresolved, and ends with `_SCOPE_TAIL`.

Check ids are short and stable, as in section 8.1.

### 11.5 `integrity/ledger.py`

Synthesis-fidelity figure extraction (INT-LEDGER-0xx) reads scientific notation (`3.0e8`,
`6.67 × 10⁻¹¹`, `1.2*10**6`) through `stem.numbers.scan_number`, so `6.67 × 10⁻¹¹` is one figure,
not 6.67 and 10. Since the STEM review (S6 and the ledger-units policy, section 23.3) figures are
compared as typed quantities (`ledger.figure_changes`):
- **value and precision are one spelling.** Every numeral, plain or scientific, and every figure in
  words is spelled `d.ddd e<exponent>` with exactly its significant figures
  (`canonical_spellings`): `3.0e-2`, `0.030` and `30e-3` are the same figure; `3.0e8`,
  `3.0 × 10⁸` and `300000000` too, because the trailing zeros of an integer written without a
  point may be significant. Before the review a scientific figure was spelled by its exact value
  only, so `0.03 J` passed silently for `3.0e-2 J` while the faithful `0.030 J` was refused;
- **distinct outcomes.** A figure whose value no cited source states (in any spelling, precision or
  commensurable unit) is introduced (INT-LEDGER-023) and the source figure dropped
  (INT-LEDGER-024); a figure with a source's value but other significant figures is a precision
  change (INT-LEDGER-023, "changes the precision", and nothing dropped); a change of form only is
  nothing;
- **units are a separate attribute.** The unit written after a figure (symbols the SI reading
  accepts after a figure, or unit words; per cent is left out) is read by the STEM unit table. The
  same numeral with a unit that is not the source's is a unit change (INT-LEDGER-023, "changes the
  unit": `2.0 kg` for `2.0 g`, `2.0 kJ` for `2.0 J`, `2.0 s` for `2.0 m`); the same quantity in a
  commensurable unit is a conversion and no finding when it agrees within half a unit in its last
  written place (`0.0020 kg` for `2.0 g`, `90 min` for `1.5 h`, `298 K` for `25 °C`), a precision
  change when the significant figures cannot agree (`0.002 kg` for `2.0 g`; not applied across an
  offset scale), and units of different dimensions never convert; a unit stated on one side only
  is no change;
- **beyond the scanner's bounds** (an exponent over 99) a figure has no exact value and is no
  token, but it is compared by its normalised written form (`1e100` and `1e999` differ, `1e100` and
  `1.0e100` are a precision change); its parts are never read as figures.

### 11.6 Relay history (`channel/bus.py`)

A relay runs without the request (no Given or show-that check, no coverage, no word bound) and a
router forward re-checks nothing, so before the STEM review a report delivered with a failed Given
check could be relayed or forwarded ACCEPTED with no finding. Now every delivered transmission of a
report or synthesis is recorded (`TranslatorChannel.payload_history`), and:
- a relay or forward of a report references every earlier delivered transmission of the same
  report (its arrival first) in `TransmissionReceipt.history`, and carries each unresolved finding
  of theirs (an error or warning of the receipt's own, a subject finding of warning severity) as
  INT-HIST-001 with the original severity, claims, reports, agents, documents and signed result,
  once, unless the new receipt states the same finding itself; a receipt's own carried findings are
  referenced at the receipt they came from, never carried twice;
- a synthesis references the transmissions of the reports it cites (listed, or holding a claim it
  cites) and carries what names a claim it cites; report-level findings stay in the referenced
  history, and so (close round 2 of the argument diagnosis, DIFF-05) do the subject findings about
  a report's paragraphs or sentence style (ES-STR-, ES-STY-, HI-STR-: `bus._LAYOUT_PREFIXES`), since
  a synthesis restates claims, not paragraphs;
- a refused transmission is no history; a clean arrival is referenced and carries nothing, so its
  relay stays ACCEPTED; INT-HIST-001 never blocks delivery (a carried error leaves the receipt
  ACCEPTED_WITH_FINDINGS with that error);
- at most 32 earlier receipts are referenced (the first always) and 64 findings carried (the last
  says how many more the history lists).

---

## 12. CorePack and quant in SI reading

`quant.py` gains a keyword-only `reading: QuantReading` parameter on `extract_quant_checks`
and `undecided_quant_statements`. `QuantReading(name, si, profile)` is a frozen, hashable
dataclass (`stem/si_reading.py`) and is part of the extractor's cache key; `si` switches every
SI rule below on, and `for_profile(key)` gives the reading for one subject profile. The
SI-specific figure patterns, unit reader, views and statement splitter live in
`stem/si_reading.py`, which imports nothing from `branches` or `channel`. `GENERAL`
(`quant.GENERAL`) is the pre-STEM extractor byte for byte, and every existing quant test runs on
it; `tests/branches/test_quant_si_reading.py` pins it against a 570-text reference corpus
recorded before `QuantReading` existed. `SI_READING` changes the following:

- **Scale words.** Only spelled-out words (thousand, million, billion, trillion, quadrillion,
  bn) are scales. m, k, K, M, A and g are never scales, so `500 mm to 2 m` and `300 K` are read
  correctly.
- **Units.** A figure followed by a unit symbol is read through `stem.units` into an SI value
  and a dimension.
  - Pairs are comparable when their dimensions are equal: `500 g to 1.0 kg` is a doubling,
    `2 kg to 500 g` is a fall of 75 per cent, and `3.0 A to 1.5 A` pairs.
  - Different dimensions are undecided, with the reason named.
  - A relative change on an affine scale is undecided.
- **Numbers.** Scientific notation, `−` and `-` are read, and a U+2212 sign on a stated change
  is honoured. A relative change is taken against the magnitude of the earlier figure, so a
  rise from −4.0 to −2.0 is a rise of 50 per cent. Repeated folds are read: "halved twice" is
  ×¼; "doubled three times" is ×8.
- **Band.** The band is sign-aware, `|C − S| ≤ tol·|C| + floor`, encoded with `ite`. `S = 0` is
  decided by the same inequality.
- **View.** quant reads the SI quant view (`si_quant_view`), in which every relation-bearing
  math span (LaTeX, a math run, verbal arithmetic, chemistry, code, tables) is a placeholder
  while quantities (`500 g`) stay readable. quant sees only prose relations and `StemPack` only
  math relations; the same statement is never checked twice.
- **Sentences.** Statements are split by the STEM segmenter (`si_statements`), so CORE-QNT-001
  paragraph and sentence numbers match the STEM claims `s<paragraph>.<n>`.

`CorePack(reading)` reads two more views of the same length, both of which mask an inch or
arcsecond mark attached to a number: `si_prose_view` (math, code and quantities masked) and
`si_quote_view` (the original with code masked). It uses them for three things:
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
- **Engine.** About 4 to 20 ms per check, measured on the design-time probes. Probe totals:
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
- **Measured** (`tests/stress/test_stem_stress.py`, figures in `tests/stress/results/stem.json`
  and docs/STEM_RESULTS.md): every target is met. A typical 3-part Physics answer: p95 188 ms
  over 60 answers. A 128-check answer: 1.22 s. The mixed adversarial input: best of 5 runs
  1.09 s. Two single-pattern inputs at 400,000 characters (`1e1e…`, unclosed `$`) take 1.6 to
  1.8 s; the target is for the mixed input, and these are recorded, not asserted.

---

## 14. Safety (no eval)

- **No string evaluation.** No `eval`, `exec`, `compile` (only `re.compile` of constant
  patterns), `__import__`, `importlib`, `pickle`, `marshal`, `sympify`, `parse_expr`,
  `ast.literal_eval`, `subprocess` or `os.system`, and no library that evaluates strings. No
  sympy dependency.
- **`Fraction` input.** `Fraction` is constructed only from integer pairs, or from digit
  strings the lexer has already validated.
- **Enforcement.** Three tests parse source with the standard `ast` module (the tests use
  `ast`; the package does not):
  - `tests/stem/test_front_end_safety.py` scans every module of `stem/`. It fails on a
    forbidden name (`eval`, `exec`, `compile`, `__import__`, `globals`, `locals`, `vars`,
    `open`, `input`, `breakpoint`, `setattr`, `delattr`, …), a forbidden attribute (`.eval`,
    `.sympify`, `.parse_expr`, `.literal_eval`, `.loads`, `.system`, `.import_module`,
    `__globals__`, …), a `getattr` or `hasattr` with a computed attribute name, or an import
    off the allowlist. The allowlist is the standard-library modules `re`, `fractions`,
    `dataclasses`, `functools`, `typing`, `hashlib`, `unicodedata`, `math`, `enum` and
    `types`, the package's own modules, and one shared module,
    `adapters.history_specialist.sentences`. A meta-test checks that the scan catches each
    forbidden form.
  - `tests/stem/test_checks_safety.py` scans the checks-stage modules again: `math` only in
    `enclosures.py` (the cross-check), and no `Fraction` built from a string constant.
  - `tests/stem/test_parser_claims.py` scans `adapters/stem_specialist/`,
    `branches/stem_pack.py`, `stem/si_reading.py`, `stem/hub_hooks.py` and `branches/quant.py`
    for the forbidden names and attributes and for imports of `pickle`, `marshal`,
    `subprocess`, `importlib`, `sympy`, `ast`, `os`, `builtins`, `code`, `codeop` and `runpy`.
- **Audit at the end of the build.** A search of all of `src/epinoic_logic` for `eval(`,
  `exec(`, bare `compile(`, `sympify`, `parse_expr`, `__import__`, `pickle`, `marshal`,
  `literal_eval`, `globals()`/`locals()`, `subprocess`/`os.system`, sympy or numexpr imports,
  `ast` use and dynamic `getattr` found none used on agent text: every `compile(` is a
  `re.compile` of a constant pattern; the one `eval(` is Z3's `model.eval` on an already
  compiled symbol (`engine/procedures.py`); `importlib.import_module` appears only in `cli.py`
  and `service/app.py`, on fixed names or an adapter id from the operator's configuration within
  the `epinoic_logic.adapters` namespace; and every `getattr` uses a literal attribute name or
  iterates a fixed tuple of schema fields.
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
13. Adding the Limits digest into `Binding.binding_digest`. At the STEM merge the engine recorded
    non-default Limits on the signed result only, which kept the hand-off binding formula unchanged.
    Done since engine 0.4.0 (external review of 12 October 2026): the binding carries
    `limits_digest` for non-default limits (appended to the binding digest; the default formula is
    unchanged), and `check_result_binding(..., limits=...)` compares them with the policy the
    receiver requires, so a nonlinear STEM result passes only a receiver that names `nonlinear`.
14. Non-SI conventions beyond the table (imperial units except °F and the inch mark), and
    locale number formats beyond the decimal-comma rule.

---

## 16. Test plan

New tests are added. No existing test is weakened or deleted. The two recorded routing
assertions (section 10.2) are replaced by assertions of equal strength.

Every file named below exists. The implementation added these test files beyond the plan:
`tests/stem/test_hub_hooks.py` and `tests/stem/test_si_reading.py` (stage `branch`),
`tests/stem/test_reading_extensions.py` (99 tests pinning the module fixes the corpus found,
stage `corpus-eval`), `tests/stem/test_arena_stem_mutations.py` (19 tests of the arena
mutations), `tests/branches/data/quant_general_reference.json` (the 570-text reference of the
general quant reading), the corpus builder `tests/stem/data/` (`build_stem_corpus.py`,
`corpus_dsl.py`, `corpus_items.py`, `corpus_items_more.py`, `corpus_lib.py`) and the labelled
fixture corpus `tests/fixtures/stem/corpus/` (84 answers written before implementation; see its
README). The corpus has 558 items (236 correct, 292 mutants, 30 rounding-only controls), above
the 120 and 240 floors below.

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
  - the 13 silent passes observed before STEM support are all caught or named.
- `scripts/arena/stem_mutations.py` and `scripts/arena/run_arena.py`: STEM subjects and
  mutation injection in the arena harness for contained multi-agent runs. Overseer audits
  read receipts only.
- `tests/stress/test_stem_stress.py` (`-m stress`): the targets of section 13.
- `docs/STEM_RESULTS.md`: the measured results of the contained run, with no claims beyond
  them.

**Not run in this build.** The overseer audits of each stage's tests and the STEM arena with
live specialists. The STEM build runs as one integrated system with the main arena, which merges
this branch (round 7 when it is ready, otherwise round 8) and tests STEM there with a STEM lens
and a STEM fixer; its results go to docs/STEM_RESULTS.md, section "Integrated arena results".

---

## 17. Implementation stages (sequential; disjoint files)

`core` and `engine` may run in parallel. `checks` needs both. `branch` needs `checks`.
`corpus-eval` needs `branch`. Each stage ends with the full suite green, plus an overseer
audit of its own tests. No stage writes a file another stage owns.

**Status.** All five stages are implemented on `stem-build` and the full suite is green
(docs/STEM_RESULTS.md, section 8). The per-stage overseer audits were not run in this build;
they are folded into the integrated arena (section 16, "Not run in this build"). Beyond the
lists below, stage `corpus-eval` also touched front-end modules to fix readings the corpus
exposed (`checks.py`, `document.py`, `lexer.py`, `nodes.py`, `numbers.py`, `parser.py`,
`relations.py`, `scope.py`, `segment.py`, `spans.py`, `units.py`; docs/STEM_RESULTS.md,
section 7), each fix pinned by `tests/stem/test_reading_extensions.py`. The labelled fixture
corpus was committed right after this design and before any implementation.

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

Since the end-to-end simulation of 16 October 2026 a caller outside the process names the same
policy: `POST /v1/verify` and `epinoic-logic verify` take `policy` (`linear`, `nonlinear` or the
integrity layer's `joint`; `engine.policies.NAMED_POLICIES`, `named_policy`), applied exactly as
the channel applies it (the `rlimit` cap included), so a STEM check decides over HTTP as it did on
the channel. In that simulation seven STEM checks the channel decided under `nonlinear` came back
UNSUPPORTED (E201) over HTTP, because the request could not name the policy
(`tests/service/test_named_policy_over_http.py`). A pack still names only `linear` or `nonlinear`.

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
- **ENGINE_VERSION 0.2.0 → 0.3.0:** the result records non-default Limits (stage `engine`).
- **POLICY_VERSION 2026.10-v2 → 2026.10-v3:** named pack policies; alias and word-boundary
  changes; the new `stem` profile; eligibility rule 4.
- **TRANSLATOR_VERSION 0.2.0 → 0.3.0:** the STEM profile text.

IR_VERSION stays 1.0.

The fixes of the external review of 12 October 2026 bumped all three again (ENGINE_VERSION 0.4.0,
POLICY_VERSION 2026.10-v4, TRANSLATOR_VERSION 0.4.0; history in `version.py`), and every result now
also binds the build, schema and policy identity (`engine/identity.py`), so a STEM result of an
earlier release is never taken as current. For the STEM checks: the unsat core is always computed,
the binding covers non-default limits (item 13 of section 15), and the encoding devices grounded
`arithmetic_fact` are listed as unverified dependencies (section 7.6). No STEM decision changed.

Recorded behaviour changes, for the overseer audit and the user's sign-off:
1. STEM subjects route to the `sciences`, `mathematics` and `computer_science` branches
   instead of `generic`, which changes two existing assertions (section 10.2).
2. A branch check whose ENTAILED result carries E108 is now undecided, not ok.
3. A check expecting UNSATISFIABLE that comes back SATISFIABLE is now failed, not undecided.
4. Subject aliases match on word boundaries.
5. INT-SUBJ-001 and INT-SUBJ-002 now carry claim ids.
6. New codes: INT-SUBJ-004 and BR-INTERNAL-001.

Every other non-STEM behaviour is unchanged by construction (P5).

Recorded behaviour changes of the STEM review fixes (section 23), which are channel and integrity
rules and so reach every branch:
7. A request item's command words never address it alone when it names anything else (INT-REQ-004
   on any branch: "We calculate 2 + 2 = 4." addresses no "Calculate the profit margin"); on the STEM
   branches an item that names what it asks for in notation only ("Solve 3x + 5 = 20") needs a claim
   about that notation.
8. A relay or forward of a report, and a synthesis, carry the unresolved findings of the earlier
   receipts they build on (INT-HIST-001) and reference those receipts (`TransmissionReceipt.history`).
9. The synthesis ledger compares figures by value, significant figures and unit: a precision change
   is named as one (no INT-LEDGER-024 for it), a unit change is INT-LEDGER-023, and a faithful
   conversion is no finding.
10. New codes: ST-CLAIM-001 and INT-HIST-001.

---

## 19. Refinements made during implementation

The sections above now describe the code. These are the points where the implementation
refined or departed from the original design text, collected for the overseer audit:

1. **Relation outcomes.** Five outcomes, not three: `check`, `undecided`, `binding`, `formula`
   and `context` (section 1, item 2; section 4.7).
2. **Claim ids per branch.** `s<p>.<n>` in `sciences`, `m<p>.<n>` in `mathematics`, `c<p>.<n>` in
   `computer_science`, so two STEM branches never share a claim id on one task. The parser
   takes the request text from the channel (`accepts_request_text`), and a heading line with
   no content of its own is role `structural` (section 9).
3. **Hub hooks.** Every hook method takes the subject profile key; `coverage_terms` also offers
   computing command words for a claim that holds a planned computation; the channel guards
   every hook call (section 11).
4. **Engine bounds for the nonlinear policy.** `rlimit` is capped at `NONLINEAR_RLIMIT`
   (a lower caller value is kept), and assertions above polynomial degree 24
   (`NONLINEAR_MAX_DEGREE`) are refused with E201 before compiling (D2).
5. **Check budget.** The STEM checks of one report run under an 8 s wall-clock budget; checks
   left when it is spent are INT-SUBJ-002 (section 11.2).
6. **Failure severity.** `stem-sub`, `stem-cnv` and `stem-res` also fail at warning severity
   (INT-SUBJ-004) when a D3b booklet value was used or a unit was unknown, as `stem-eq` does
   (section 8.1).
7. **Truth tables** are decided as an entailment (Form E), not a satisfiability query
   (sections 7.7 and 8.1).
8. **Withheld relations.** A relation whose operands the front end may have cut is withheld
   with ST-PARSE-001 rather than decided (section 8.1).
9. **Readings added by the corpus.** Σ over integer bounds (at most 24 terms) is read as its
   terms; order chains, ratio equalities, factorisations inside a chain, functions and
   derivatives evaluated at a point, Boolean name definitions and truth-table columns they
   head are read; `ms⁻¹` has two readings; complex values are named undecided (sections 4.5,
   4.7, 6.3; docs/STEM_RESULTS.md, section 7).
10. **Spans and statements.** Chemical equations and bare quantities are span kinds;
    derivation lines are statements, not spans (sections 4.2 and 4.3).
11. **Bounds.** ST-LIM-002 also names math spans beyond 1,024 per report; the IR bounds of the
    checks stage are in `to_ir.IR_LIMITS` (section 4.9).
12. **Safety enforcement.** `stem/` imports nothing from `ir/` or `engine/` (problems leave it
    as data); three AST scans enforce the rules over `stem/`, the STEM adapter, the STEM pack,
    the hub hooks, the SI reading and `quant.py` (section 14).
13. **Quant reading.** `QuantReading(name, si, profile)` switches the SI rules; the SI patterns,
    views and statements live in `stem/si_reading.py` (section 12).

Known gaps measured at the end of the build (for example `yr` missing from the unit table,
function names other than `f`, `g` and `h` read as products, `|\vec{v}|` unparsed, exponential
equations undecided) are listed in docs/STEM_RESULTS.md, section 9.

---

## 20. Merged with the round-7 development branch (one translator)

The STEM branches were built on a fork taken at arena round 4. The merge into the development
branch, which carries the verified round-5 to round-7 arena fixes, makes them one translator:
Physics, Chemistry, Biology, ESS, Mathematics (AA and AI) and Computer Science answers go through
`StemTextParser`, and every rule round 7 added to the generic parser for those subjects is kept
by it. On the round-7 answers the STEM parser delivers the generic parser's claims claim by
claim (the same texts, roles, proposed kinds, figures, quotations, materiality and supports)
under the STEM ids, and the hub reads the same request items
(`tests/stem/test_merge_round7.py`).

### 20.1 Layout rules (`stem/layout.py`, `spans.py`, `segment.py`)

The round-7 rules that decide where a claim starts and ends are the generic parser's, restated
in `stem/layout.py` (the STEM package imports nothing from `branches`;
`tests/stem/test_layout.py` asserts the patterns are the same):

- a line that opens with `=` or `≈` continues the equation of the line before it, and a line
  after a comma or a connective, or a soft-wrapped prose line, continues its line; every other
  line break ends a statement, so each line of working, list item, table row and result is a
  statement of its own (an equation continued over three lines is one derivation statement,
  its links still read across the lines);
- part labels and label-only lines (`(a) [2]`, `Part (a) — find — 3 marks`) and mark
  annotations (`[1]`, `[1 spare]`, `  M1`, `(A1)`) are furniture: blanked from the statements
  (and from the claim texts, which leave interior markup out), never read as maths;
- a table is one statement per row; the separator row is furniture.

### 20.2 Roles (`adapters/stem_specialist/parser.py`)

The roles, materiality and supports are the generic branch's round-7 reading
(`generic_parser.assign_roles`, run on units built from the STEM statements): notes, questions
and headings are `other`; the answer of each part is material; a consequence or a judgement
rests on the claims before it; a caveat is no support; supports never form a cycle. The STEM
refinements of section 9.2 apply on top only where round 7 did not rule: a code block is a
material point; a "Given:" or "Working:" heading and a table header row with no words are
`structural`; a binding or a law is `evidence` when the answer presents it as given (under a
"Given:" heading, led by "Given", "Taking" or "Using", or where the generic reading would take it
for the paragraph's point), while a law or a binding written as a line of working ("V = ε − Ir"
over its substitution, "At rest means v = 0:") keeps the round-7 role; a judgement that restates
a checked result is `quantitative`; a reason sentence is a `link`. Two section 9.2 behaviours
change with the merge: a link supports the point and rests on nothing (no support cycle,
CORE-STR-001), and a consequence rests on the claims before it.

### 20.3 Request items

A multi-part request yields one item per part on every branch (the round-7 rule). The STEM
imperatives still split sentences, but the rubric's "Show your working (with units)." or "Show
full working." is no item (`channel/request_parser._SHOW_WORKING_RE`).

### 20.4 Readings corrected (false INT-SUBJ-001 on genuine round-7 answers)

Each was fixed where the reading went wrong; the same fault written into the same line is still
named (`tests/stem/test_round7_false_errors.py`):

1. A thousands group inside brackets is one numeral when it is an operand of arithmetic
   (`(1,000 ÷ 2^10 = 0.98)`); a list or a pair stays separate numbers (`lexer._thousands_operand`).
2. A stated value with its absolute uncertainty (`1620 − 20 = 1600 ± 32 counts min⁻¹`) is a band:
   the computed value must lie in it (`checks._uncertainty`; only a binary `±` between two written
   values stated for a computed side with no `±`).
3. A power written after a value continues the run (`1600 e^(−8k)`, `C0 e^(−kt)`).
4. A line that writes the preceding relation with values put in (`1/R = 1/R₁ + 1/R₂`, then
   `1/R = 1/4.0 Ω + 1/6.0 Ω`) reads the written values for the symbols (substitution readings),
   so the step is checked with them (`relations._premise_substitution`).
5. A symbol reused in a later part for a value the request gives (`R = 2.4 Ω` in (a), the 6.0 Ω
   resistor in (d)) is read there, not checked against the other part's binding; a value the
   request does not give is still checked (`relations._given_in_another_part`).
6. The order relations of a sentence stated under a condition (`For 2 < t ≤ 3, …, so v < 0.`) are
   context, not claims about the values stated for t and v elsewhere (`_CONDITIONAL_RE`).
7. A prose value after a result cue restates the last chain before it in its part, and only a
   chain that computes a value: never an older chain past one that ends on an order relation,
   never a value stated for a symbol (`relations._results`).

### 20.5 Readings added (the round-7 STEM mutations)

All 15 STEM mutations of the round-7 answers are named with their code on the injected claim
(`tests/stem/test_round7_mutations.py`):

1. A word formula in brackets (`(final − initial) ÷ initial × 100 = (80 − 40) ÷ 40 × 100 = 100%`)
   is part of its run (`spans._RunFinder.mathy_operand`).
2. A written evaluation of a formula the answer states in the part, in a shape the formula does
   not repeat (`a = dv/dt = 6 − 6t`, then `At t = 1: a = 6 − 6(1)`), is checked as the formula under
   the stated values (a `sub` check that evaluates, Form S over the bindings); a formula with `±`
   is not evaluated (its roots are checked by `stem-sol`). The formula stated through a derivative
   is kept; the derivative itself stays undecided (section 7.8).
3. An indefinite integral of a polynomial with the antiderivative the answer states
   (`∫6t dt = 3t²`, a constant of integration allowed) is an `alg` check from the trivially true
   premise `D = D` to `D = integrand`, where D is the derivative of the stated antiderivative.
   **The STEM pack forms D by the power rule (`stem/calculus.py`, exact rational coefficients),
   not the engine**; the check description says so, and the engine decides that the two
   polynomials agree for every value of the variable. Definite integrals, non-polynomial
   integrands and derivatives stay outside the encodings.
4. A step between two relations in which one unknown appears only in powers of e with integer
   multiples of it of one sign (`800 = 1600 e^(−8k)`, then `e^(−8k) = 1/2`) is read in
   `u = e^(−k)` with `u > 0` (an exact change of variable; the relation records it in
   `positive` and the check adds the side condition).
5. Computer Science: a trace step that gives a variable a value in prose ("mid = 1 gives 3 < 9,
   so low moves to 2") is checked against the update rule the answer states for that variable
   earlier in the part (`low = mid + 1`), when the step's own clause states a value for every
   other variable of the rule (`relations._assignments`).

The arena harness's marker for a substitution stays inside one statement: it stops at the end of
its sentence and leaves a closing mark annotation out (`scripts/arena/stem_mutations._link_marker`),
as every claim does under the round-7 rules; the mutated texts and the expected codes are
unchanged.

### 20.6 Tests changed by the merge

Each was rewritten to assert the same behaviour as strictly or more strictly, or to the round-7
rule where the two branches disagreed (listed with the reason in the merge record):
`tests/adapters/test_overseer_round7.py` (claim-id test: STEM letters plus claim-by-claim
equivalence with the generic parser), `tests/channel/r7_support.py` and
`tests/channel/test_round7_fixes.py` (recorded ids resolved through the generic parser's numbering
of the same claims), `tests/channel/test_stem_channel.py` and `tests/stem/test_hub_hooks.py` (one
item per part on the default reading), `tests/stem/test_parser_claims.py` (no support cycle; a
consequence rests on earlier claims), `tests/stem/test_segment.py` and
`tests/stem/test_relations.py` (an equation continued over lines is one statement; one statement
per table row), and `tests/branches/data/quant_general_reference.json` (the GENERAL reading's
reference regenerated on the development branch; byte identity still required).

---

## 21. Detection fixes from the end-to-end simulation (run1)

The end-to-end simulation of the website-to-backend flow (sixteen specialists, the arena harness on
their genuine answers) left six injected faults unnamed. Each was traced to its cause; the answers
are kept as test data (`tests/channel/data/e2e_run1_material.json`) and every fix is pinned by
`tests/stem/test_e2e_run1_detection.py`. All six are now named, each as the harness injects it (the
injection is the base one; 21.3), and none is excused: an injection no finding names is a miss.

### 21.1 Gaps in the checks

1. **Decimal and fractional powers of a closed value** (ch-e1b: `[H⁺] = 10^(−8.2) = 9.31 × 10⁻⁹`,
   and the same line with the pH substituted wrongly). The exponent reader named every non-integer
   exponent 'a fractional or decimal power', so no pH line was checked. A closed base with no unit
   raised to a closed exponent that is no integer is now a `RealPower` node (`nodes.py`,
   `parser._real_power`): the exponent's tokens may be figures, signs, operators, brackets and
   `\frac` only, and the base and the exponent must hold no symbol, unit, angle, per cent or `±`.
   A rational value is exact, as the exact-value table gives `sin 30° = 1/2`: a positive rational
   base whose numerator and denominator are exact q-th powers for the exponent p/q
   (`16^(3/4) = 8`, `4^1.5 = 8`, `(8/27)^(2/3) = 4/9`; `enclosures.exact_real_power`, exact integer
   roots, at most 30 digits), so `x² = 16^(3/4) ⇒ x = ±2√2` is proved exactly. Any other value
   (`10^(−8.2)`, `2^(−3.5)`) is the enclosure of `exp(x·ln b)` for a positive base (`to_ir._real_power`),
   cross-checked against `math.pow` within 10⁻⁹ of the value; `0^x` with x > 0 is 0; a zero base
   under an exponent that is not positive is ST-UNDEF-001 and a base that is or may be negative
   ST-UNDEC-001 (which real power the writer means is not chosen). A check that uses the enclosure
   is Form S, so correct work within the tolerance band passes (`10^(−8.2) = 6.31 × 10⁻⁹` holds) and
   the slip does not. An algebra or inequality step that holds such an irrational power stays
   undecided (ST-UNDEC-001, the power named), as every step did before the power was read: a step is
   compared exactly (only a side that is one written value gets a band, section 8.1), so
   `I = I₀ × 2^(−3.5) = 0.088 I₀`, correct to 2 s.f., could only become a false error. A symbolic
   exponent (`10^(−pH)`) and a symbolic or dimensioned base stay undecided as before (a power of e of
   an expression in symbols is read in a model evaluation only, item 5).

   **The antilogarithm of a concentration scale** (the ch-e1b substitution as injected:
   `[H⁺] = 10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³`, the pH 8.2 substituted as 5.2). A calculation with no unit
   stated in a unit is read as written and in SI (section 6.4). For a lone power of ten that reading
   is blind to a class of faults: every unit prefix is an integer power of ten, so the power read as a
   bare number in SI (10^(−5.2) mol m⁻³) matched the stated 6.31 × 10⁻⁹ mol dm⁻³ exactly, and an
   exponent 3 too small, the injected substitution, passed. A lone power of ten with no unit
   (`10^(−8.2)`, `10^{-5.8}`, and the integer `10^(−7)` too) set against a value in a unit of
   concentration is now the concentration in mol dm⁻³, the unit the pH, pOH, pKa and pKb scales are
   defined in, and is compared with the stated value in SI only (`checks._antilog_as_concentration`;
   the reading is named "the power of ten read in mol dm⁻³"). The recorded injection is UNSATISFIABLE
   (INT-SUBJ-001 on s1.2), and so are the same fault 10³ the other way (`= 6.31 × 10⁻¹² mol dm⁻³`) and
   an integer pH substituted (`10^(−4) = 1.0 × 10⁻⁷ mol dm⁻³`); the genuine lines hold, and so does the
   same concentration stated in any unit of concentration (`10^(−3.3) = 0.501 mmol dm⁻³`,
   `10^(−8.2) = 6.31 × 10⁻⁶ mol m⁻³`, `5.01 × 10⁻⁴ M` in chemistry). Every other calculation keeps both
   readings of section 6.4: a power of ten stated in a unit of another dimension (`E = 10^(13.8) =
   63 TJ`, the Richter energy in joules; `V = 10^(−3) = 1 dm³`), a per cent, `M` where it may be mega,
   and a product or quotient (`[OH⁻] = 10^(−14)/10^(−8.2)`). So a unitless product stated in a prefixed
   unit still absorbs an error of exactly the unit's factor (`c = 0.25 × 4 = 0.001 mol dm⁻³` passes in
   SI): the documented reading, which no injection of the harness produces.
2. **The LaTeX thin space between digit groups** (mai-e1: `21\,131.40 - 18\,000 = 6131.40`). The
   number reader knew the Unicode thin spaces but not `\,`, so every operand written with it was cut
   ("unexpected '131.40' after an operand") and the answer had no check at all. `scan_number` now
   reads `\,` between an integer part of one to three digits and groups of exactly three as a
   thousands separator, one kind of separator throughout; anything else stays LaTeX spacing.
3. **A relayed specialist named by its subject** (hi-e1a: `The Mathematics specialist states that
   "the model is not aly good fit for 1923"`). A relayed report authored by
   `mathematics-aa-specialist` was named only "mathematics aa specialist", so the router's own name
   for the colleague in its hand-off ("attribute them to the Mathematics specialist") named no text:
   the misquotation was credited to none and only reported unverifiable (CORE-SRC-003, a warning).
   `adapters.sources.specialist_names` adds the subject's first word ("mathematics specialist") when
   the agent id names a course or qualifier after it, and for Mathematics the spellings "maths
   specialist" and "math specialist"; the History, English and STEM parsers and the
   crediting rules share it, so the quotation is credited to the colleague's report and refuted
   there (INT-REQ-003, naming the altered word). A sentence that names no text keeps the earlier
   rule (unverifiable unless an own supplied text holds the words).
4. **An integer power beyond 12 of a closed value, and a value stated in prose for a named
   quantity** (mai-e1 substitution: `18\,000 = M \times \frac{1-(1+\frac{0.065}{12})^{-60}}{\frac{0.065}{12}}`
   → `\frac{4-…}`). Two gaps kept the changed equation from any check. First, the integer-power
   bound (12, section 4.9) made `(1 + 0.065/12)^{-60}` unsupported although its base is a closed
   value. A closed base with no unit raised to an integer beyond 12, up to 1000, is now one value: a
   `RealPower` whose exponent is the written integer (`parser._make_pow`). The encoder writes its
   exact value when it fits one literal (`2^{20} = 1048576`, `(−1.5)^{13} = −1594323/8192`: an
   integer power of a negative base takes the sign of its parity), and otherwise the outward-rounded
   interval power of the base (`Interval.power`, decided in Form S: `1.003^{144}`), refusing a value
   beyond about 10^±300 (ST-UNDEC-001) and a zero base under a power that is not positive
   (ST-UNDEF-001). A power of an expression in symbols keeps the bound (it is a polynomial of that
   degree), so the nonlinear policy's degree bound is unchanged; a step that holds an enclosed power
   stays undecided, as one holding an irrational power does (item 1). Second, the answer states M's
   value only in prose, under the name it gave the symbol: "Let $M$ be the monthly payment in
   euros." … "Her monthly payment is €352.19." Such a value is now a stated root of the equation in
   that symbol (`relations.named_quantities`, `_described_roots`): checked by `stem-sol`
   (membership), so the changed equation, whose root is 29.75, is refuted with INT-SUBJ-001 on m3.1
   and m5.1, and the genuine one (root 352.1907) holds. The reading is narrow, so a misreading never
   decides anything:
   - the definition is one letter, in inline maths or not, after "let" or "letting" (with be,
     denote, represent or stand for), after "where" or "with" (with is, =, denotes, represents,
     stands for, or no verb), or opening its statement (with is, denotes, represents or stands for),
     then a determiner and words only; the description stops at a figure, sign or bracket and
     before a relative clause or a conjunction, and a trailing "in <unit>" also gives the shorter
     name ("monthly payment in euros", "monthly payment");
   - the clause that states the value is that description word for word, with at most a connective
     and a determiner or possessive before it and a verb of identity (and a currency sign) after it;
     its sentence opens with no condition ("If the rate is 5%, the monthly payment is …" is not
     read); and nothing follows the value to the end of the sentence but a currency, time or count
     word, a rounding note or a mark annotation: no qualifier, negation, comparison or question;
   - the value is a decimal with no unit (a whole number in prose may be a count the context
     rounds up or down, as 16 buses for 15.3); the symbol has no value stated in maths anywhere in
     the answer; the definition is in the value's part (or in none), and the equation is the latest
     one written before the value in that part whose one unknown is the symbol, with no unit, sign
     choice, construct outside the encodings or function of the unknown;
   - a prose value is approximate by nature, so the root ranges over its rounding interval widened
     by the '=' slack of R2 (τ = 1/100 of the value): a payment rounded up a cent holds, the changed
     annuity factor (twelve times the payment) does not. The failure severity is error: both
     statements are the report's own, read word for word.
5. **An exponential model evaluated at an argument** (the maa-e1a substitution:
   `(b) P(t + 1) = P₀e^(k(t + 1))` → `P(t + 4)`). Three readings kept the changed link from any
   check: `P(t + 4)` was the product P·(t + 4) (a function name other than f, g and h is no function
   to the parser), a power of e of an expression in symbols was outside the encodings, and the request's
   model `P = P₀e^(kt)` names no variable. A **model** is now a function of one variable defined with
   a power of e, or of a positive closed base, whose exponent holds symbols: `P = P₀e^(kt)` in the
   request, `C(t) = C0 e^(−kt)` or `A(t) = 500 × 2^(t/3)` in the answer (`models.py`; kept apart
   from the formulas, which are premises of steps and substitutions). Its variable is the one it names,
   else the one symbol of its expression that the answer's applications put an argument in for
   (`P(t + 1)` and `P(t)` name t; a run the answer declared as one name, `kt` after `kt = ln 2`, is read
   as the product of its letters when only that names the variable). An **application** is the model's
   letter glued to a bracket that holds exactly the argument (`P(t + 4)`, `P(6)`; not `P (t + 4)`), told
   apart from a product by the written text alone. An equality with an application becomes a
   `stem-mod` check, the model's expression at the written argument against the other side: some value
   of the variables (the model's variable and every symbol with no stated value), and of the stated
   symbols within their stated values, must satisfy it (Form S). The encoder reads every power B^X of
   an exponent in symbols through positive variables: with X = c + Σ qᵢ·mᵢ (c rational, qᵢ rational,
   mᵢ distinct monomials) and sᵢ the largest step of which every coefficient of mᵢ in the link is an
   integer multiple, B^X = B^c · Π uᵢ^(qᵢ/sᵢ), uᵢ = B^(sᵢ·mᵢ) > 0, bounded by the enclosure of
   B^(sᵢ·range) when every symbol of mᵢ has stated values. Every real solution gives such uᵢ, so the
   reading only widens the solutions: UNSATISFIABLE proves that no value satisfies the link, and
   SATISFIABLE never claims that it holds for every value. The changed link asks
   `P₀e^(k(t + 4)) = P₀e^(k(t + 1))`, that is 250·u₁·u₂⁴ = 250·u₁·u₂ with u₂ = e^k in [e^2.045, e^2.055]
   (k = 2.05 to 3 s.f.) and u₁ = e^(kt) > 0: UNSATISFIABLE, INT-SUBJ-001 on m3.1. The genuine
   `P(t + 1) = P₀e^(k(t + 1))` and `P(6) = 250e^(6k)` hold, and round 7's maa-p7b gains three such
   checks (`C(8) = 800`, `C(T) = ½C0`, `C(40) = 1600 × 2^(−5)`), each satisfiable. The reading is
   narrow, so a misreading never decides anything: only `=`; no written decimal on either side or in
   the model (a rounded figure would need its rounding interval: `N(t + 5) = 0.5 N(t)` holds only
   within it), no unit and no other construct outside the encodings; exponents are polynomials with
   rational coefficients (degree at most 4, at most 8 monomials per base, no power beyond 12 of one
   variable); a base is e (mathematics and Computer Science readings only: in the sciences e may be
   the elementary charge) or a positive rational; the model's own definition is no check; and a model
   whose variable no application names (`P(6)` alone could stand for t or for k) gives none. A
   description ("Let t be the number of months") is not read for the variable: it can name a
   parameter as readily. The superscript letter of `eᵏ` is still outside the grammar (the span ends
   there), so the rest of that chain keeps its reading.

   A letter defined as two models (`Model A: N = 100e^(t/5)`, `Model B: N = 100 × 2^(t/3)`) is read in
   each definition: one pair of sides per combination of the definitions of the letters a link applies
   (at most 4), and the link must hold in one of them, so no definition is chosen for the answer
   (`Model B: N(t + 3) = 2N(t)` holds whichever is stated last; `N(t + 3) = 3N(t)` holds under neither).
   A definition whose variable nothing names (`P = 250e^(6k)`, an evaluation written as a definition)
   is none.

   **Steps over applications** (found while measuring this item; at 22d6a5b too). Every application of
   a letter other than f, g and h is a product to the parser, so consecutive evaluations of a function
   were an algebra step under that reading and refuted: `N(10) = 200`, then `N(15) = 100`, was
   `10N = 200 ⊢ 15N = 100`, an error on correct work, and so were `C(2) = 13`, `C(3) = 18` after
   `C(t) = 5t + 3` and `N(t + 1) = 2N(t)`, `N(t + 2) = 4N(t)` after `N(t) = 100 × 2^t`. A letter the
   request or the answer defines as a function of one variable (`C(t) = …`, the letter glued to a
   bracket holding one symbol that the right side uses; or `P = P₀e^(kt)`, `V = 20000 × 0.8^t`, a power
   whose exponent holds symbols) is now read as f is (section 4.7): an evaluation at a value
   (`N(15) = …`) is no step, and a step whose relations hold an application at an unknown is
   ST-UNDEC-001 ("a step involving an application of a function the text defines"). Each evaluation is
   still checked by itself where the model reading covers it (`stem-mod`), and a bracket after a letter
   the text does not define as a function keeps its product reading and its steps (`ε = I(R + r)`, then
   `I = ε/(R + r)`).
6. **Unit exponents written in ASCII** (the independent verification of this repair). `3 m s-1` was
   `3 m s − 1`, a subtraction of a bare number from a quantity, so correct work in ASCII units was an
   error before any of these fixes (`v = 6 ÷ 2 = 3 m s-1` refuted with c = 3, r = 2;
   `c = 0.5 × 2 = 1 mol dm-3` with r = −2), and the decimal powers of item 1 stated that way
   (`[H+] = 10^(-3.3) = 5.01e-4 mol dm-3`) became errors as soon as the power was read. An exponent
   glued to its atom is now the atom's power (`parser._ascii_unit_exponent`, `units.parse_unit(...,
   ascii_exponents=True)`): a hyphen-minus or plus and one digit (`s-1`, `dm-3`, `J kg-1 K-1`,
   `mol2 dm-6`), one digit 2 to 9 after an atom of two or more letters (`cm3`, `dm3`), and one such digit
   after a slash (`m/s2`, `kg/m3`). Never read so: more digits or a decimal (`300 K-273`), a space on
   either side of the sign, a sign followed by an atom of the same dimension (`5 m-3 m = 2 m` stays a
   subtraction of lengths), and a one-letter atom's glued digit right after a number (`2 m2` may be
   2·m₂, and `H2` is a formula). The span finder reads such a digit as part of the unit, and only the
   parser asks for the reading: the translator's typed quantities, the SI reading and the segmenter
   read a digit inside a unit as before.

### 21.2 A harness defect (`scripts/arena`)

7. **The part label in the marker** (maa-e1a substitution: `(b) P(t + 1) = P₀e^(k(t + 1))` →
   `P(t + 4)`). The marker kept the part label "(b) ", which no claim carries, so no injected claim
   was found; it now leaves a part label out as it leaves a mark annotation out, and m3.1 carries it.
   With the model evaluation (item 5) the injection is named on m3.1.

### 21.3 A rule withdrawn: no injection is excused

An earlier fix for items 4 and 6 reported a STEM injection no finding names as NOT APPLICABLE
(outside the transport count) when the harness's own regular-expression reading found a symbol with no
"x = value" binding in the changed expression and no formal check moved. An independent
verification showed that it excused real misses: values stated in prose ("a ball of mass 0.50 kg",
"a spring of constant 200 N m⁻¹") were never read, so a substitution of the request's g in
`E = m × 6.81 × 20 = 98.1 J` and a slip in `E = 0.5 × k × 0.15² = 5.25 J` were reported not
applicable (27 of 27) where 22d6a5b counts both as misses (27 of 29). In maa-e1a, k and P₀ are
stated, and in mai-e1 the answer states M's value in prose: both misses came from limits of the
encodings (items 4 and 6), not from injections that cannot apply. The rule is withdrawn: every injection no finding names is a failure, and when the receipt names the injected
claim undecided the reason quotes it (`run_arena.undecided_on`, `undecided_on_injected_claims`).
Those two probe misses remain gaps of the encodings (a value stated in the request's prose for a
symbol the answer uses without naming it), counted as misses.

A second change of the harness is withdrawn as well. An earlier version of item 1 changed the
injection instead of the reading: a figure written as the exponent of a power of ten moved its first
decimal digit (`10^(−8.2)` → `10^(−8.5)`) and an exponent with no decimal digit was no site, because a
change of the leading digit (8.2 → 5.2) is a factor of 10³ that the SI reading absorbed. That made
the run1 count rise while the recorded fault, `10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³`, still passed as a
satisfied check, and a test asserted that it passed. The injection is again the base one (the leading
digit of every figure moved by 3, an exponent of ten included; `stem_mutations.py`), the fault is named
at its cause (item 1), and the test asserts the error.

### 21.4 Tests changed

- `tests/fixtures/stem/corpus/stem-math-020.json` (and its copy in `tests/stem/data/stem_corpus.json`):
  the fractional-power fault `16^(3/4) = 16 × 3/4` was expected as undecided (ST-PARSE-001 or
  ST-UNDEC-001); the engine now refutes it (16^(3/4) is exactly 8), so it is expected as
  INT-SUBJ-001 alone from the arithmetic check (`FIXTURE_LABELS` in `tests/stem/data/corpus_items.py`
  pins the check kind `eq`), a stronger label. The fixture README records the change.
- `tests/stem/data/corpus_items_more.py` (`math-fracpow-1`): the relation
  `16^{3/4} = (\sqrt[4]{16})^3` is still named undecided with ST-UNDEC-001, now for the fourth root
  alone ('root of index 4'), since `16^{3/4}` is read; the corpus was rebuilt (two labels changed,
  558 items as before).
- `tests/stem/test_e2e_run1_detection.py`: the tests of the withdrawn rule (21.3), which asserted that
  the maa-e1a and mai-e1 substitutions were not applicable, are replaced by stricter ones: the mai-e1
  substitution is named INT-SUBJ-001 on m3.1, the verification's two probe misses are counted (27 of
  29), and with no finding allowed to name anything every injection of the round is a failure.
- The same file, after the second verification: the tests of the withdrawn injection change (21.3)
  are replaced by stricter ones. The test that asserted that `10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³` is no
  error now asserts that it is one, with six more faults of that kind; the ten cases of the withdrawn
  `figure_change` are replaced by four injections the base harness makes into exponents of ten, each
  named; the ch-e1b substitution is asserted as recorded (`10^(−5.2)`, UNSATISFIABLE on s1.2); and the
  tests that asserted the maa-e1a substitution as a miss now assert it named (INT-SUBJ-001 on m3.1 by
  `stem-mod`), with the genuine answer's model evaluations holding and the contained round naming all
  six faults (stem_substitution 3 of 3). Controls pin the concentration reading's limits (a volume,
  an energy, a per cent and an ambiguous `M` keep both readings of section 6.4). The test that a
  contained round with no finding allowed to name anything fails every injection now also asserts
  the failure reason of every injection the receipt names undecided (it quotes the receipt's
  ST-UNDEC findings and still counts the miss), which the replaced maa-e1a miss test asserted for
  that record.
- New: `tests/stem/test_ascii_unit_exponents.py` (item 6: correct work in ASCII units holds, faults in
  them are errors, the subtractions and the one-letter forms that keep their reading, and the unit
  table read with the exponents only when the parser asks) and `tests/stem/test_model_evaluations.py`
  (item 5: model evaluations with no solution are errors, correct ones hold, a letter defined as two
  models is read in either, round 7's maa-p7b gains three checks that hold, the links the reading
  does not cover keep their old reading, consecutive evaluations of a function the text defines are
  no algebra step while a fault in one of them is still named, and a bracket after a letter that is
  no function keeps its product reading and its step).

---

## 22. External review of 12 October 2026: findings S1, S2, S5, S7 and part scope

An external review of the STEM integration (reviewed commit of the published STEM release;
development source 83e97e9) reported seven findings and a policy concern. Findings S1, S2, S5 and
S7 and the part-scope policy are fixed here, each at its cause in `stem/`; S3, S4 and S6 (coverage
verbs, structured claim ids, scientific notation in the ledger) are outside the STEM checks and
handled separately. Each is pinned with the reviewer's probes and negative controls in
`tests/stem/test_review_stem_checks.py`: the correct answer still passes, a really wrong answer still
fails, and run on the source before the fixes 40 of its 63 behavioural tests fail (the other 23 are the controls,
which pass before and after; the 13 remaining tests exercise the new helpers and the recorded policy). As the
review recommends, invariance tests pin one verdict for harmless parentheses (around a group, a value, a root, an
absolute value's argument and a temperature's number), each with its wrong twin still failing.

1. **S1, a grouped temperature lost the Celsius offset.** `T = (20 + 5) °C = 298.15 K` was an error
   and `= 25 K` passed, while `T = 25 °C = 298.15 K` passed. The planner classifies the grouped side as
   arithmetic, and the encoder converted `WithUnit` (and its interval) with the factor alone, so the
   offset was applied only in explicit conversions between two literals. Now (section 6.1) the
   point-or-difference decision is made per relation in every comparing check, and a temperature is
   converted once, on the value its side states (`to_ir.Encoder._affine_point`): `(20 + 5) °C` is the
   evaluated `25 °C`, exactly as the literal is. A side that combines such a temperature with other
   terms is never converted term by term; its SI reading is refused (`to_ir.AffineUndecided`), so the
   relation is undecided, or checked in its as-written reading only with failure at warning severity.
   The same path now keeps the offset for order relations (`30 °C > 295 K`), restatements, Given
   values, substituted values and symbols bound to a temperature (their domain carries the kelvin
   value, `SymbolDomain.values_si_abs`). Fahrenheit controls are covered.
2. **Symbols bound in different units** were compared as written when the relation itself wrote no
   unit (`m₁ = 500 g`, `m₂ = 1.0 kg`, `m₁ < m₂` was an error). The reading modes now take the units of
   the symbols' bindings into account (section 6.4). Found while fixing S1; same mechanism.
3. **S2, explicit exactness was ignored.** With "Calculate 1/2 exactly, without rounding.",
   `1/2 = 0.51` passed (half a last-digit unit plus 1 %) while `1/2 = 51/100` failed. Now (section 5.2,
   R2) the tolerance policy carries intent first: exactness stated by the answer beside the relation,
   or by the request (per part) for a relation between pure numbers, makes the comparison exact for
   every spelling; a rounding the request asks for keeps the written-digit tolerance; and over exact
   operands a stated decimal earns no relative slack from its spelling, so `0.51` and `51/100` get the
   same verdict under every policy (both fail for 1/2) while correct roundings (`1/3 = 0.33`,
   `√2 = 1.41`) pass. Under a stated rounding the stated value is a rounding whatever its spelling
   (no exact mode): `7/3 = 2` under "to the nearest integer" and `1/3 = 33/100` under "to 2 decimal
   places" pass as `1/3 = 0.33` does, and with no rounding stated they remain exact claims and fail.
   The same rule holds in an evaluation under bindings and in an algebra step, where a rounded value
   used to earn the 1 % slack over exact operands (`2x = 1 ⇒ x = 0.51` passed while `x = 51/100`
   failed). Each check records the policy that decided it (`PlannedCheck.tolerance`, its
   description and the signed problem's notes). The phrases are read by `tolerance.exactness_phrase`
   and `rounding_phrase` ("exactly two reasons" and "need not be exact" state no exactness).
4. **S5, a root set's verdict depended on its order.** `x² = 4 ⇒ x = −2 or x = 2` was an error: the
   chain reading took the connective for a step to the first member alone, checked under the
   principal-root condition `x ≥ 0`. Now (section 4.7) once a root set of two or more members is
   recognised, a step from its equation to one member is context (`case`) and its ST-ALG-001 note is
   withdrawn; `stem-sol` checks the set (membership and completeness), so every order and `±` get the
   same verdict, and a wrong member still fails. A `±` before a rounded value (`x² = 2 ⇒ x = ±1.41`)
   is read in the step as two rounded values; the step compared them exactly and was an error,
   while `x = −1.41 or x = 1.41` passed.
5. **S7, plain absolute values were masked as a table.** A line opening with `|` and holding two bars
   was a table, so `|−2| = 2` got no check and an INT-REQ-012 error, and `|−2| = 3` escaped. Now
   (section 4.2) a block of such lines is a table only with a Markdown delimiter row or the shape of
   a truth table; `|−2| = 2` is checked as `$|−2| = 2$` is.
6. **Part scope.** Substitutions matched any binding of a symbol, so in `(a) x = 2, y = x + 1 = 5;
   (b) x = 4, y = x + 1 = 3` each wrong result matched the other part's binding and both passed. Now
   (section 4.6) a binding holds in its own part from where it is stated (`checks._scoped`): both
   checks fail with INT-SUBJ-001, while a value carried forward from an earlier part that states it,
   a value given in the same statement ("…, where x = 2"), the request's values and a written
   substitution of any value in scope still pass. An evaluation uses the value in force; a rebinding
   in the same part makes its failure a warning. An order relation compares stated values only when
   its symbols have a value of its own part or one value elsewhere (`relations._bound_in_part`); a
   symbol given several values elsewhere (the request's "at t = 0 and t = 8", then `t > 40` in part
   (c)) is an unknown. ST-SCOPE-001 stays an informative note, and its message now states the rule.

**Residuals, recorded rather than hidden.** Within one part, a written substitution may still match
any value stated before it (the written value shows which was meant); a symbolic evaluation after a
rebinding is checked against the latest value at warning severity. A relation combining an offset
temperature with other terms against another scale is undecided, not decided. The written-digit
half-width of an integer with trailing zeros (`300 K` is ±50 when its operands have one significant
figure, R1) is unchanged. Under a stated rounding a root written as an integer or a fraction is still
checked as an exact root (`stem-sol`), and a restated fraction (`stem-res`) keeps h = 0.

**Measured on recorded rounds** (copies replayed with `scripts/arena/run_arena.py`): round 3 46/46
and round 7 177/177, as before the fixes, with all 15 STEM mutations of round 7 named. No receipt of
either round changed its status, its codes or its findings' codes, severities and claims. Four round-7
mutation errors changed wording only (the rule's short form; two substitution errors, now entailment
checks, quote the engine's counterexample instead of an unsatisfiable reading), and two round-7
answers changed check forms only, with their variants (cs-t13: a substitution decided by entailment
instead of satisfiability; maa-p7b: an inequality about an unknown no longer planned as a
comparison). The full suite stays green.

---

## 23. STEM review fixes: request coverage, claim attribution, typed ledger figures, relay history

The external review of the STEM integration (12 October 2026) reported, among others, four integration
findings and two policy limits that concern the channel, the integrity layer and the claim mapping: S3, S4,
S6, the ledger's units and the relay history. Each was reproduced with the reviewer's probe on this code,
fixed at its cause, and turned into regression tests that keep the passing controls passing and the wrong
answers failing.

### 23.1 Request coverage (S3; `channel/bus.py` `_coverage`, `stem/hub_hooks.py`)

Before: for "Calculate the acceleration. Calculate the force. Calculate the wavelength." the answer
"2 + 2 = 4." was ACCEPTED with all three items addressed by its one claim; "Find the distance." likewise.
The STEM hook lent the computing command words to every claim that computes, and one shared word met the
lexical threshold. Now (section 11.2) an item's command words and the instructions on the form of its
answer are no evidence on their own: an item that names anything else is addressed only by a claim that
shares one of its topic terms (its own words, or the words the hook lends: dimensions, unit names, relation
kinds, a derivative's "gradient", a component's direction) or that the hook finds about the item (a symbol
the item asks for, enough of the item's own figures). The three items above are now unaddressed (three
INT-REQ-004); `a = (20 − 0)/4.0 = 5.0 m s⁻²` still addresses "Calculate the acceleration" and the receipt
stays ACCEPTED. The rule is the channel's, so it holds on every branch ("We calculate 2 + 2 = 4." addresses
no "Calculate the profit margin").

The same cause had two further forms, fixed with it:

| Item, answer "2 + 2 = 4." | Before | Now |
| --- | --- | --- |
| "Solve 3x + 5 = 20.", "Simplify √50.", "Find u₆ and S₅.", "Convert 72 km h⁻¹ into m s⁻¹.", "Given f(x) = x² − 3x, find f(5).", "Calculate v if d = 120 m and t = 8 s." (an item whose words are all command words, naming what it asks for in notation) | addressed, ACCEPTED | unaddressed, INT-REQ-004 |
| "Calculate the acceleration of a trolley that reaches 4 m/s in 2 s." (two single-digit figures shared by coincidence) | addressed | unaddressed, INT-REQ-004 |
| "Calculate the speed if d = 120 m and t = 8 s." answered `t = 2 + 2 = 4` (a symbol the item gives a value for) | addressed | unaddressed, INT-REQ-004 |

The genuine answers to each of these items still address them (`3x = 20 − 5 = 15, so x = 15/3 = 5`,
`√50 = √25 × √2 = 5√2`, `v = d/t = 120/8 = 15 m/s`, `a = 4/2 = 2 m s⁻²`, ...). A computing claim now also
offers "evaluate", so the correct answers to "Evaluate 16^(3/4) without a calculator", "Evaluate log₁₀ 1000
exactly" and three more "Evaluate" items, which were wrongly unaddressed, address them.

Calibration on every item of the 558-item corpus and every recorded answer of rounds 1 to 7 (614
transmissions, 670 items), against the code before the fixes: no item lost its coverage; 13 items that were
wrongly unaddressed are now addressed (three correct truth tables and their three mutants, which change a
row and not the coverage; six answers to "Evaluate" items, five correct and one mutant; a differentiation);
119 attributions were narrowed (a claim that counted for an item only through a shared imperative, such as
an intermediate step or a restated Given line, no longer does) and 8 changed claims (now through a unit, a
percentage, a truth-table row, or the computations that evaluate an item instead of the line that restates
its imperative); nothing changed in rounds 1 to 7. Tests: `tests/channel/test_stem_review_coverage.py`.

### 23.2 Claim attribution (S4; `branches/stem_pack.py` `_ClaimMap`)

Before: a structured report whose claims `s1.2` ("2 + 2 = 5.") and `s1.1` ("3 + 3 = 6.") carry the familiar
ids in the other order got the failed check and INT-SUBJ-001 on `s1.1`, the correct claim, and the passing
check on `s1.2`, the false one: the claim map trusted an id that looked like its statement id before any
span or text. Now statements map by source span and text (section 9.1); an id is the statement's one claim
only when its text agrees (it overlaps the span, it is the text the parser gives the statement, or the
two-way substring rule holds), and a disagreeing id is ST-CLAIM-001 (warning) naming both claims. The same
report now has the failure on `s1.2` and the pass on `s1.1`; with ids `first`/`second`, or with the parser's
own claims, nothing changes. A repeated line ("x = 2 + 2 = 5" in two parts) maps to its own occurrence.
Tests: `tests/branches/test_stem_review_claim_map.py`.

### 23.3 Typed ledger figures (S6 and the ledger-units policy; `integrity/ledger.py`)

| Source → synthesis | Before | Now |
| --- | --- | --- |
| `3.0e-2 J` → `0.030 J` (notation only) | INT-LEDGER-023 error, INT-LEDGER-024 | nothing |
| `3.0e-2 J` → `0.03 J` (2 → 1 significant figures) | nothing | INT-LEDGER-023 "changes the precision" |
| `3.0e-2 J` → `0.031 J` (another value) | INT-LEDGER-023, -024 | INT-LEDGER-023, -024 |
| `2.0 g` → `2.0 kg`; `2.0 J` → `2.0 kJ` | nothing | INT-LEDGER-023 "changes the unit" |
| `2.0 g` → `0.0020 kg` (conversion) | INT-LEDGER-023, -024 | nothing |
| `2.0 g` → `2000 kg` | INT-LEDGER-023, -024 | INT-LEDGER-023, -024 |
| `1e100` → `1e999` (beyond the scanner's bounds) | nothing | INT-LEDGER-023, -024 |

INT-SYNTH-012 (the paraphrase was not formally checked) stays on every row: number and unit preservation is
still not a formal check of the claim. Tests: `tests/integrity/test_stem_review_ledger.py`.

### 23.4 Relay history (`channel/bus.py`, `channel/contracts.py`)

Before: with the request "Given v = 20 m/s and t = 4 s, calculate the acceleration.", an answer stating
`v = 40 m/s` arrived with a failed Given check (`stem-giv-1`) and INT-SUBJ-004, but its relay to the
combinator was ACCEPTED with no finding (the relay form builds no Given check) and the router's forward
ACCEPTED with no check. Now (section 11.6) both receipts reference the arrival and carry the INT-SUBJ-004 as
an INT-HIST-001 warning on `s1.1` with its signed result; a synthesis citing `s1.1` carries it too, one
citing other claims only references it. Tests: `tests/channel/test_relay_history.py`.

### 23.5 Tests changed by the fixes

Each asserts the same rule as before or a stricter one:
- `tests/integrity/test_stem_ledger_figures.py::test_spellings_meet_across_notations`: the spellings of
  `3.0e8`, `3.0 × 10⁸` and `300000000` still meet; the assertion that the less precise `3e8` is a spelling of
  `3.0e8` became `3.0e8` is one and `3e8` is not (the precision-less spelling is what let `0.03 J` pass for
  `3.0e-2 J`).
- `tests/channel/test_peer_exchange.py::test_router_forwards_a_delivered_report_unchanged_and_the_peer_quotes_it_through_the_hub`,
  `tests/channel/test_round2_fixes.py::test_a_specialist_cannot_relay_a_colleagues_report_or_overwrite_the_held_copy`
  and `::test_supersession_names_forwards_and_quoting_reports_and_a_synthesis_citing_the_old_report`: each
  asserted that a faithful forward of a report is ACCEPTED, while the report's arrival had left a heuristic
  INT-REQ-004 warning open. Each now asserts that the forward is delivered, adds no finding of its own, carries
  exactly the arrival's unresolved findings as INT-HIST-001 (same severity, claims and message), references
  the arrival receipt, and is ACCEPTED exactly when the arrival left nothing open
  (`tests/channel/history_support.assert_carries_exactly`).

### 23.6 Measured

Full suite: 4443 passed, 45 deselected, 4 expected failures (before the fixes: 4353 passed; 90 tests added,
4 rewritten, none removed); the arena-rule harness tests pass (27). No stress test was run. Arena replays of the recorded rounds on copies, with the code before and after
the fixes (`scripts/arena/run_arena.py`; functional rate as defined there):

| Round | Functional before | Functional after | STEM mutations named | Genuine records with an error (before → after) | Genuine records with an error or warning | INT-HIST-001 findings |
| --- | --- | --- | --- | --- | --- | --- |
| r1 | 30/30 | 30/30 | — | 3 → 3 | 7 → 7 | 4 |
| r1-adv | 150/151 | 150/151 (the planted empty answer is still REJECTED) | — | 6 → 6 | 21 → 21 | 0 |
| r2 | 46/46 | 46/46 | — | 2 → 2 | 7 → 7 | 3 |
| r3 | 46/46 | 46/46 | — | 2 → 2 | 8 → 9 | 7 |
| r4 | 46/46 | 46/46 | — | 1 → 1 | 9 → 11 | 3 |
| r5 | 46/46 | 46/46 | — | 2 → 2 | 7 → 7 | 2 |
| r6 | 46/46 | 46/46 | — | 0 → 0 | 8 → 8 | 4 |
| r7 | 177/177 | 177/177 | 15/15 | 18 → 19 | 37 → 39 | 11 |

The rises in the last three columns are relays, forwards and syntheses that now carry what their reports'
arrivals left open (in r7 the router's forward of the History peer report that arrived with an INT-SUBJ-001
error, and the synthesis citing that claim); no new finding was raised on any answer's own content. The
functional rate does not judge whether a finding is true; the receipts are judged by the overseers.

---

## 24. Argument diagnosis: STEM reference knowledge, named STEM diagnostics and the STEM false errors

This section records the STEM part of the argument-diagnosis work, which builds on the shared contract of named
diagnostics (`named.py`, engine 0.5.0). It covers:

- the closed STEM reference;
- the nine named STEM diagnostics of the code table;
- the end-to-end false errors of the STEM and general branches (B2, B7, B17, B25, and a psychology grounding alarm);
- the rerun lens findings on the STEM front end, the prose-arithmetic reader and the cross-report check.

Every diagnostic follows one rule: it only adds information.

- It never upgrades a status, never turns a failed or undecided check into a pass, and never weakens a check.
- It can make a result not releasable, never more releasable.
- It is computed deterministically from the engine result, the IR, the document the front end read, the request and
  the closed reference data. Nothing in the answer or the request is executed.
- Each diagnostic has a positive test and a clean control.

The scope statement of section 1 is unchanged: a named diagnostic, like a check, is a property of the encoding.

### 24.1 Phase 0: the merge interaction

On the tree that merges the two STEM review branches (sections 22 and 23), 8 tests of
`tests/stem/test_review_stem_checks.py` failed. Genuine one-line answers left their item unaddressed (INT-REQ-004):

- "1/2 = 0.50" to "Calculate 1/2 exactly, without rounding.";
- "x² = 4 ⇒ x = ±2" to "Solve the quadratic equation.";
- "|−2| = 2" to "Calculate the absolute value of negative two.".

The cause: the coverage rule of section 23.1 needs topic evidence, and the STEM hooks lent none for these shapes. The fix
in `stem/hub_hooks.py`:

- A claim that writes the item's own expression token for token is about the item. This takes one linear pass of the
  STEM lexer. A lone figure, a sign, a prose word or units set apart write no expression.
- An equation in one unknown lends its degree ("quadratic" for x² = 4).
- An operation written in notation lends the words a request uses for it: |x| lends "absolute" and "modulus", log lends
  "logarithm", and sin and cos lend their names.

Unrelated arithmetic still addresses nothing. Tests: `tests/stem/test_review_merge_interaction.py` (16). The five review
test files pass unchanged.

### 24.2 The closed STEM reference (`stem/reference_data.py`, `stem/reference.py`)

The reference is exact data in the pattern of `stem/constants.py`. Nothing in it is evaluated, and `stem/reference.py`
reads it. It holds:

- `QUANTITIES` (70 entries since repair round 1, 24.11; 79 since repair round 2, 24.12): for each symbol, the IB subject profiles, the quantity's name, its dimension (`units.Dimension`), its SI
  unit and the quantities it is ambiguous with in a profile:
  - p is momentum in physics and pressure in chemistry, biology and ESS, and each is ambiguous with the other; in physics
    p and P are pressure too (repair round 2), so a physics p or P is fixed only by its result's unit or the request;
  - P is power, ambiguous with pressure;
  - V is potential difference in physics and volume in chemistry, biology and ESS;
  - Q is heat, ambiguous with charge;
  - c is specific heat capacity, ambiguous with the speed of light and a concentration;
  - T is temperature, ambiguous with a period and a tension;
  - λ, f, ρ, I, R and the guide's other symbols are listed too.
- `FORMULAS` (15 laws): the data-booklet laws for each quantity and profile, as an exact coefficient and terms:
  E_k = ½mv², ΔE_p = mgΔh, p = mv, F = ma, W = Fs, P = W/t, V = IR, Q = mcΔT, v = fλ, a = Δv/Δt, I = Δq/Δt, ρ = m/V,
  n = m/M, f = 1/T and, in physics, the pressure p = F/A (repair round 2).
- `BOOKLET_LAWS` (94 laws, repair round 1; 102 since repair round 2): the laws of the data booklets of physics, chemistry,
  biology, sports science, ESS and mathematics, each a law of one quantity, which the front end reads as exact data (`reference.booklet_laws`) for
  the form check ST-REF-002.
- The cue tables of the diagnostics below: extrapolation caveats, working cues and commands, change markers,
  noun-phrase stopwords and comparison phrases.

`fixed_quantity(symbol, profile, result_dims=..., request_text=...)` fixes a symbol's quantity only when the dimension
guard agrees and one of these holds:

- the symbol is unambiguous in the profile;
- the units of its stated result decide it;
- the request names the quantity ("Calculate its kinetic energy").

Otherwise it returns nothing, and no ST-REF-001 can follow. That is a miss, never a false alarm.

`coefficient_free_dimension` reads the dimension of a right-hand side with its numeric coefficients dropped, however they
are spelled, so `0.5 × m × v`, `m × v / 2` and `½mv` have one dimension. The same rule fixes ST-DIM-001 on such
coefficients: a decimal factor is dimensionless unless the reference names it a constant.

### 24.3 Named STEM diagnostics

| Code | Defect | Decided by | Failure appears as | Positive | Control |
| --- | --- | --- | --- | --- | --- |
| ST-REF-001 | stem_wrong_formula | front end | ST-REF-001 warning naming the booklet formula | s02, s02b | s00; an ambiguous p with no unit |
| ST-REF-002 | stem_wrong_formula | front end (24.11) | ST-REF-002 warning naming the booklet laws | E_k = mv² (the ½ dropped) | E_k = ½mv² |
| ST-UNIT-003, *written* case | stem_unit_error | engine (`unit` companion `stem-<kind>-<n>u`) | INT-SUBJ-001 error labelled stem_unit_error | s03b, s03d | s03k, s03dk |
| ST-UNIT-003, *traced* case | stem_unit_error | engine (`unit` companion) | INT-SUBJ-004 warning (a reading the report did not state) | s03a | s03k |
| ST-STEP-001 | stem_invalid_step | engine (`op` check, an identity) | INT-SUBJ-004 warning | s05 | s05c |
| ST-STEP-002 | stem_invalid_step | front end | ST-STEP-002 info | `x² = 3x`, then "Dividing both sides by x: x = 3" | the same with `(x ≠ 0)` stated |
| ST-ROUND-001 | stem_rounding_changes_conclusion | engine (`rnd` check) | INT-SUBJ-004 warning | s04 | s04c |
| ST-RANGE-001 | stem_extrapolation | front end | ST-RANGE-001 warning | s07 | s07c; the same answer with a caveat |
| ST-WORK-001 | stem_missing_working | front end | ST-WORK-001 warning | s08 | s08c |
| ST-GIVEN-002 | stem_contradictory_givens | front end | ST-GIVEN-002 warning | f05b | c06-givens; a rebinding in part (b) |
| ST-GIVEN-003 | stem_contradictory_givens | front end (24.11) | ST-GIVEN-003 warning | a probability above 1; "mutually exclusive" against the request's P(A ∩ B) = 0.1 | the addition rule with the stated intersection |
| ST-SCOPE-002 | stem_symbol_conflict | front end | ST-SCOPE-002 warning | s06 | s06c; a rebinding after "Next," |

What each diagnostic decides:

- **ST-REF-001.** The answer's law for a symbol whose quantity is fixed (24.2) has a right-hand dimension, with
  coefficients dropped, other than that quantity's. A symbol that appears on both sides is an equation, not a law, and
  gets nothing. Sciences profiles only.
- **ST-UNIT-003, written.** Both sides carry units of one dimension with different factors, or a per cent sign
  converts one side only (`reference.as_written_reading`). The check beside the companion decides the relation under
  both readings. The companion fails exactly when the numbers hold as written and fail in SI.
- **ST-UNIT-003, traced.** Bare numbers of the working repeat the numbers of bindings stated in non-SI units
  (`d = 2.5 km`, `t = 10 min`, then `v = 2.5/10 = 0.25 m s⁻¹`). The companion reads each such number in its binding's
  unit. Every numeral of the working must be accounted for, and the reading must give the stated unit's dimension.
  The report never wrote that reading, so a failure is a warning.
- **ST-STEP-001.** The prose before a step states an operation: "adding 4 to both sides", "dividing both sides by 2",
  "squaring both sides". Applied to each side of the preceding equation, that operation must give the next line's
  sides, in either order, for every value of the unknowns. Exactly one stated operation is read; a combined one is not
  guessed.
- **ST-STEP-002.** A step divides by an expression of the unknown with no `≠ 0` stated. The step's own check, or the
  root check, decides whether the solution sets differ.
- **ST-ROUND-001.** A comparison against a threshold uses a value the working itself rounded (`… = 0.246 s ≈ 0.25 s`).
  The comparison must keep its truth with the value before the rounding.
- **ST-RANGE-001.** A model the answer states is evaluated at an input outside [min, max] of a series the request gives
  (three or more values of one quantity in one unit), with no caveat. Sciences profiles only.
- **ST-WORK-001.** The request asks for working: "show your working", or a calculate, determine or show item worth two
  or more marks. The answer states one result with no formula, substitution or working line. Computer Science is
  exempt.
- **ST-GIVEN-002.** A symbol of a Given or Data statement is bound again to another value in the same part, with no new
  symbol, and a later substitution uses it.
- **ST-SCOPE-002.** A symbol is bound twice in one part to different values whose noun phrases name different
  quantities ("the car's speed", "the speed of sound"), with no change marker before the second binding, and a later
  substitution uses it.

An engine-decided diagnostic carries its defect on the check (`PlannedCheck.defect`, copied to `FormalCheck.defect`), so
the channel's INT-SUBJ-001 or INT-SUBJ-004 for its failure is labelled with that defect. A front-end diagnostic is a
structural finding, and its defect is the code's canonical label. No severity exceeds the code's maximum
(`named.NAMED_CODES`).

Check ids gain new kinds: `op`, `sys` (stem-soundness-5 in 24.6) and `rnd`, plus the `u` companions.

Tests:

- `tests/stem/test_reference_formulas.py`
- `tests/stem/test_units_symbolic.py`
- `tests/stem/test_steps_operations.py`
- `tests/stem/test_rounding_range_working.py`
- `tests/stem/test_givens_symbols.py`

### 24.4 The B2 false errors: eight classes, twelve sentences

The end-to-end run reported twelve false INT-SUBJ-001 errors on correct STEM work. Each is fixed at its cause in the
reading. `tests/stem/test_e2e_b2_classes.py` pins each sentence with a wrong twin (the same construct, wrong) that still
fails with INT-SUBJ-001.

| Class | Sentence (case) | Misreading | Fix |
| --- | --- | --- | --- |
| a count before an operator | "4 categories − 1 = 3" (bi) | read as `− 1 = 3` | a run reads a count noun's number before it (`spans._count_before`): 4 − 1 = 3 |
| a mixed-unit compound | "4 min 30 s = (4 × 60 + 30) s = 270 s" (ph) | cut to `30 s = …` | a compound quantity is the sum of its parts, read as (4 min + 30 s) with its own tokens |
| a value restated in brackets | "= 0.870 (87%)" (ph) | the product 0.870 × 87% | a run stops before a percentage restated in brackets |
| a chain cut at "…" | "= 2.084429… + 18.420681… = 20.505110…", "= 0.693147… / 2.050511… = 0.338036… months" (maa) | the ellipsis cut the chain | a decimal with a glued ellipsis (`…`, `...`, `\ldots`, `\dots`, `\cdots`) is a truncated numeral (`ExactNumber.truncated`, half-width one unit in its last digit) |
| a figure from another chain | "so about 26%" after "(1.259 − 1) × 100 = 25.9%" (ch, ess); "= 25.9%" (ess); "a fall of 0.1 pH unit" (ch) | checked against the final value of an earlier chain | a restatement is of the chain in its own statement first, and of the same quantity: a value in a named scale (pH, pOH, pKa) restates only a value in that scale, and pH is a quantity's name, not a unit; a number that is an operand of written arithmetic (the 1 of `(1.259 − 1)`) or stands in a mark annotation (`[1]`) is no stated value |
| bit groups | "1011 0110₂ = B6₁₆", "(0110 1101₂ = 109)" (cs) | 1011 and 0110₂ read apart | digit groups of 4 or 8 in base 2 (3 in base 8, 2 or 4 in base 16) before a base subscript are one numeral (`numbers.scan_grouped_based`) |
| a quoted failing test | "the final test (2 <= 1) fails" (cs) | asserted as a comparison | a comparison followed by "fails", "is false" and their kin is negated (`Relation.negated`): the answer asserts that it does not hold |
| a pair whose end is an expression | "falls from $1.60 to $2.00 − $0.60 = $1.40" (ec) | the pair read as 1.60 → 2.00 | the general reader reads a pair's end after its written arithmetic ($1.40), or withholds the pair (`branches/quant.py`) |

One more cause surfaced with the ess case. "Quote them exactly" asked for the figures as written, yet it made the CO₂
arithmetic exact. Now `tolerance.exactness_phrase` skips "exactly" after a verb of reproducing (quote, cite, copy,
reproduce, transcribe, repeat, relay) and in "exactly as given, written or stated". The arithmetic keeps the tolerance
of its written figures, and a wrong result still fails.

### 24.5 Other end-to-end items

**B7: a figure derived by two routes, pooled at its stated precision** (`integrity/cross_check.py`). Physics s2.1 and
s2.2 derive R by two routes, 230/9.57 and 230²/2200, and each states it as 24.0 Ω. The exact pooled values 24.033 and
24.045 contradicted each other (INT-CONFLICT-001).

Now `split_by_precision` handles any Real symbol that two or more claims use in their premises and bound in their
conclusions by a stated interval:

- the first such claim keeps the name;
- each later claim gets `<name>_r<k>` and one premise `|name − name_r<k>| ≤ h_first + h_k`, where h is half the width
  of each claim's stated interval;
- the premise's grounding is `arithmetic_fact` with no verification, so a result that relies on it lists it as an
  unverified dependency.

This applies to the cross-report consistency check and to synthesis entailment, where the stored results of the sources
are still matched against the sources as formalized. Routes that agree at their stated precision never contradict each
other; 24.0 against 26.0 still does. A synthesis whose sources contradicted only under exact pooling is now checked for
entailment instead of failing as inconsistent.

Found with it (formal-robustness-4, 24.6): when the only diagnostics of a failed joint check are INT-GLOSSARY-007,
charged to identified claims, those claims are set aside and the rest are checked again. Each pass sets at least one
claim aside, so the check ends, and a contradiction among the others is still named. Tests:
`tests/integrity/test_pooled_precision_b7.py` and `tests/integrity/test_joint_invalid_claim_fr4.py`.

**B17: STEM claim ids by agent** (`adapters/stem_specialist/parser.py`, `branches/stem_pack.py`). Two agents of one
STEM branch on one task, Chemistry and ESS, held the same ids (`s1.1`), so the channel named the collision
(INT-REQ-016). The parser now takes the task's agents (`task_agent_ids`; `StemTextParser.accepts_task_agents`):

- with two or more distinct agents, every id, support and self-report note carries the agent's qualifier, as the
  generic branch's ids do (`s1.1@ess-specialist`);
- with one agent, ids are unchanged.

The STEM pack's claim map also accepts the qualified spellings. The channel passes the agents (`channel/bus.py`,
`respond_text`, applied by the integration step):

    if getattr(parser, "accepts_task_agents", False) is True:
        same_branch = {r.agent_id for r in self.transmitted_reports.values()
                       if self._branch_for(r.agent_id)[0].key == branch.key}
        extra["task_agent_ids"] = sorted(same_branch | {agent_id})

The set holds the agents of this agent's branch that delivered on the task, and this agent. Agents of another branch
number their claims with their own letter (`s`, `m`, `c`), so they cannot collide, and counting them would qualify the
ids of a physics and a mathematics answer on one task for nothing (`tests/e2e/test_stem_e2e.py`, physics and maths with
a combinator, expects `m1.1`). The set is delivery-based, so a plan that names a combinator who delivers nothing keeps
plain ids. Tests: `tests/branches/test_stem_ids_b17.py`, which reproduces INT-REQ-016 with plain ids and shows it gone
with qualified ones, and `tests/channel/test_stem_task_agents_b17.py`: through the channel, Chemistry and ESS on one task
get qualified ids and no INT-REQ-016, one agent keeps `s1.1`, and physics with mathematics keeps plain ids.

**B25: worked equations of the general branches through the STEM chain checker** (`branches/packs.py`). Worked lines
(`=` chains) of Business, Economics, Geography and Psychology were named CORE-QNT-001, "not decided". Now
`worked_formal_checks` reads them with the STEM front end:

- **The view.** `quant.worked_equations` finds the equations. The view has the same length as the answer and keeps
  only each equation's phrase. Currency signs are blanked, and line breaks inside a phrase are read as spaces, so one
  equation never continues another's chain.
- **The checks.** `stem.build_document` and `build_checks` check the view under the STEM tolerance rule. The checks
  have ids `core-stem-…` and carry the claims that hold them. An equation decided this way gets no CORE-QNT-001.
- **The unit companion.** ST-UNIT-003 is a STEM convention and is not built here: '(31 − 11) ÷ 10 = 2.0%' turns a rate
  per 1,000 into per cent as written.

A derived figure that a supplied text states word for word, with three words of context on each side (four words at
least), is a transcription, not the writer's arithmetic, and gets no CORE-QNT-001. An example is "fell by 30%" in
i02c's extract. An invented figure (e02) is still named.

**PS-SRC-001** (`branches/packs.py`). A study attribution is grounded by a supplied text that names it: the surnames
and the year must stand within 120 characters in one text, as "Loftus and Palmer (1974)" does in c03-psych's summary.
A named study in no text (e05b) still fires, and so does an attribution with the right authors and a year the text
does not give. Tests:
`tests/branches/test_core_equations_b25.py`.

### 24.6 Rerun lens findings

Each finding was reproduced on this code before its fix. Each is pinned in `tests/stem/test_lens_rerun_c.py` or
`tests/branches/test_lens_rerun_c_branches.py` with the probe and a control.

| Finding | What failed | Fix |
| --- | --- | --- |
| stem-soundness-1 | a result off by a prefix or a per cent on one side passed through the as-written reading (`3 × 2.0 kg = 6.0 g`, `300/400 = 0.75 %`, `80 × 25 % = 2000`, `2.0 kW × 3.0 = 6.0 W`) | the written ST-UNIT-003 companion (24.3): each now fails, while the same working with its units right holds |
| stem-soundness-2 | a substituted (R7), restated (R8) or Given value matched within h(b) + h(w): 3 passed for 2, 30 for 20 | one value must be a rounding of the other: the larger half-width, not the sum; in Mathematics an exact integer the answer states (`Let x = 3`) has h = 0 |
| stem-soundness-3 | a symbol was matched to a coefficient the law writes | a numeral opposite a literal coefficient of the law (the 4 of 4x, the ½ of ½mv²), aligned as `nodes.align` aligns, is that coefficient, never a substituted value |
| stem-soundness-4 | the Computer Science AND dot (`A.B`) was a sentence boundary | in the Computer Science profile a `.` between two operands is AND; a full stop after an operand stays a full stop |
| stem-soundness-5 | a solution of simultaneous equations was checked against one equation plus the answer's own values | a `sys` check of the stated solution against every equation of the system, from the part or the request; the per-equation steps to its values are context |
| stem-soundness-6 | any earlier approximation word, or a substring ('linearly', 'thoroughly'), gave 5 % slack | `tolerance.approx_qualifies`: a whole word among the last words before the relation, with only linking words between |
| stem-soundness-8 | `θ = 30° = 0.524 rad` was compared as written (30 against 0.524) | a degree/radian conversion is compared in SI with π enclosed; a conversion is exact (τ = 0) unless approximate, and a whole number on the converted side carries no h |
| stem-soundness-9 | a trig function of a bare number passed under degrees or radians | an angle the request or the answer writes in degrees (or radians) fixes the reading (the angle hint), for eq, cmp and sub alike |
| stem-soundness-11 | an incomplete root set on the next line passed (`x² = 3x`, then "Dividing by x, x = 3") | in Mathematics a root line after an equation claims the full set and is checked as after `⇒`; consecutive root lines are one set; the division gets ST-STEP-002 |
| stem-soundness-12 | common wrong working was dropped silently | a step cued as factorising, expanding or simplifying is an identity check (`alg`); bits and bytes are units; `ⁿCᵣ` is an exact binomial coefficient; an inequality in an absolute value, a chained inequality step in Mathematics and a nuclear equation are named ST-UNDEC-001 |
| stem-precision-2 | a volume substituted in the unit of the concentration (cm³ bound, dm³ substituted) never matched | a substituted value also matches the binding in a sibling unit that the same working uses (`dm⁻³` of `mol dm⁻³` gives dm³) |
| stem-precision-11 | a line of grouped or truncated arithmetic counted as 0 words, so INT-REQ-012 | in the word-count view a line of written arithmetic is one maths word; a truncated numeral is read (B2) |
| parser-safety-1 | an over-long superscript run went to `int()`, raised, and emptied the document | the lexer and the unit reader bound the run (ST-LIM-001), keep the rest of the document, and keep the bad numeral inside its run |
| parser-safety-2, -7 | the number-word patterns backtracked catastrophically | `_WNUM` is an atomic group; 'and' joins number words only after 'hundred' |
| parser-safety-5 | the emphasis pattern was quadratic per line | `layout.emphasis_spans` pairs markers in one linear pass and gives the regular expression's spans (compared on 200,000 random strings when written; the test compares 20,000); `plain_line` uses it |
| parser-safety-8 | the SI total pattern was quadratic on a digit run | a lookbehind `(?<![\d.])` on the mantissa |
| parser-safety-10 | verbal arithmetic restarted after a failed chain | the scan resumes after the failed chain |
| parser-safety-11 | list markers were scanned for every line | an index of list-marker ends by line |
| parser-safety-12 | `worked_equations` rescanned earlier links | one pass finds the first operator link |
| parser-safety-13 | `2.5e3` and `2.5 × 10³` were read by their mantissa | a lookahead keeps scientific notation out of the general figure patterns |
| formal-robustness-4 | one formalization invalid in the joint problem hid a contradiction among the others | 24.5 |
| robustness-and-contracts-7 | a quoted or JSON-wrapped answer paired a chronology cue across its sentences | `history_specialist.sentences.inner_sentences` (used by the core pack, and since repair round 1 by the HI-CHR-001 proxy too) splits the inside of a wrapping quotation or JSON string again |

Two findings no longer reproduced on this code, and their probes are kept as evidence:

- stem-soundness-10: `x² = 2 ⇒ x = ±1.41` holds, and `±1.51` fails.
- stem-precision-4: the five `(k s.f.)` cases hold, and 2480 fails.

Measured after the fixes, every adversarial input stays linear:

| Input | Time |
| --- | --- |
| 200,000-character emphasis storm | 0.42 s |
| `plain_line` on 400,000 characters | 0.29 s |
| verbal arithmetic, 200,000 characters | 0.66 s |
| 200,000 characters of list items | 2.05 s |
| `_TOTAL_RE` on 20,000 characters | 0.33 s |
| `_pairs` on 20,000 characters | 0.03 s |
| SI digit run of 20,000 characters | 0.15 s |
| `worked_equations` on 20,000 characters | 0.01 s |

### 24.7 Tests changed

Both changes are in `tests/branches/test_r7_quant_packs.py`, and each states a stricter rule than before.

- `test_bm_t13_break_even_is_never_silent_and_its_margins_are_decided` asserted that the wrong worked line
  "6,000 ÷ 2.00 = 4,000" was named undecided (CORE-QNT-001). It now asserts:
  - one failed `core-stem` check, a COUNTEREXAMPLE;
  - an INT-SUBJ-001 error quoting the line, on the same claims;
  - no CORE-QNT-001 for that line.

  The margin assertions are kept.
- `test_ge_t13_dependency_ratio_is_named_undecided` became
  `test_ge_t13_dependency_ratio_is_decided_by_the_stem_checker`. It asserts:
  - exactly one INT-SUBJ-001 error on the wrong "31 ÷ 69 × 100 = 54.9", with no CORE-QNT-001;
  - the correct GE_T13 has no error, and every one of its `core-stem` checks is satisfied.

### 24.8 Residuals, recorded rather than hidden

- **stem-soundness-9.** An angle written with no unit, in a request that writes none, keeps both readings.
- **stem-soundness-12.**
  - Inequalities in an absolute value, chained inequality steps and nuclear equations are named undecided, not checked.
  - "1 500 × 2 = 30" (a space-grouped thousand) stays withheld by design, never failed.
- **parser-safety-1.** The over-long superscript run is bounded, but any other internal failure that empties the
  document is still the ST-INTERNAL-001 warning of section 8.2, by design. Its checks are missing, and they are never
  read as passed.
- **parser-safety-5, in `adapters/markdown.py`.** The same quadratic emphasis pattern was in `strip_markup`
  (`EMPHASIS_RE`; 3.7 s at 20,000 characters). The integration step applied the linear reading:
  `strip_markup` now ends with `_strip_emphasis`, which joins the text between the spans of
  `layout.emphasis_spans(s, ("**", "__", "*", "_", "`"))` and each span's body, exactly as
  `EMPHASIS_RE.sub(r"\2", s)` did. `test_ps5_the_same_linear_reading_gives_the_markdown_helpers_emphasis_with_backticks`
  compares the spans and the stripped text with `EMPHASIS_RE` on 20,000 random strings, and
  `tests/adapters/test_linear_text_readers.py` pins `strip_markup` itself (no longer a residual).
- **B25, a negative first operand.** A worked line whose first operand is negative after a label the view blanks is
  withheld as possibly cut from a longer expression (ST-PARSE-001 on the view), so it stays CORE-QNT-001. One example
  is "Percentage change = −34.50 ÷ 192.00 × 100 = −17.97%" in round 7's ec-p7a.
- **B17.** The `bus.py` change of 24.5 is applied (no longer a residual).

### 24.9 Measured

**Development corpus.** 101 cases: 44 defects and 57 controls. A warning or error on a control counts as a false alarm.
Results by tree:

| Tree | Named | Caught, not named | Missed | False alarms | Clean controls |
| --- | --- | --- | --- | --- | --- |
| contract (be6723c) | 9 | 25 | 10 | 41 | 16 |
| Phase 0 (48255f9) | 9 | 26 | 9 | 40 | 17 |
| this section | 20 | 22 | 2 | 30 | 27 |

- **STEM family.** All 12 defects are named, with 0 false alarms and 8 of 8 controls clean.
- **End-to-end family.** The false alarms fall from 31 to 21:
  - the six B2 answers;
  - three B20 answers;
  - the B7 physics pair.

  None of the remaining false alarms carries INT-SUBJ-001, PS-SRC-001, INT-CONFLICT-001 or CORE-QNT-001. They come from
  the channel's coverage and constraints, the ledger, the source checks and the claim display: INT-REQ-003, -004 and
  -005, constraints, INT-LEDGER-020, GROUNDING:FAILED, DISPLAY:COUNTEREXAMPLE, ES-* and CORE-SRC-003.
- **Missed.** The two missed defects are f07 and i01b, outside STEM.

**Suite.** 5792 passed, 45 deselected (stress), 4 expected failures, in 278 s (before: 5628 passed). The tests changed as follows:

- 162 tests were added, and the safety scan of section 14 covers the two new reference modules (2 more cases);
- 2 tests were rewritten to a stricter rule (24.7);
- none was removed or weakened.

Run against the Phase 0 source:

- 134 of the 162 new tests fail: 54 fail outright, and 80 sit in three modules that import the new readers;
- the other 28 pass both before and after: they are the controls, the wrong twins and one reading invariant.

No stress test was run.

**Arena replays.** Every recorded round was replayed on copies with `scripts/arena/run_arena.py`, once with the Phase 0
source and once with this source:

| Round | Functional, Phase 0 | Functional, now | Receipts changed |
| --- | --- | --- | --- |
| r1 | 30/30 | 30/30 | none |
| r1-adv | 150/151 (the planted empty answer is REJECTED) | 150/151 | none |
| r2, r3, r4, r5, r6 | 46/46 each | 46/46 each | none |
| r7 | 177/177 | 177/177 | 50 records of 7 answers (all variants) |

In r7:

- **bm-p7a, bm-t13, ec-p7a, ec-t13, ge-t13** (B25). The worked lines are checked by `core-stem` checks, and every
  check holds on the genuine answers. Their worked-arithmetic CORE-QNT-001 warnings go: bm-t13 and ge-t13 become
  ACCEPTED, and ec-p7a keeps one, on the line of 24.8 (its CORE-QNT-001 on a derived figure in prose, g8.7, is
  unchanged). The relay of ec-p7a's report in bm-p7a carries what the arrival leaves open (section 23.4): one
  INT-HIST-001 instead of four.
- **mai-t13.** Relations with truncated numerals (`…`), named ST-UNDEC-001 before, are now checked, and all hold. Five
  ST-UNDEC-001 warnings go, and two lose the words "an ellipsis".
- **ph-t13.** One restatement check, `stem-res-1`, is added, and it holds. It checks the "so 16 W" of
  "P = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W" against the chain in its own statement (24.4).

No record gained an error, and no record gained a warning on anything not already named before. The one CORE-QNT-001
that is new by its claims narrows an earlier finding: ec-p7a's warning on g8.2 to g8.6, and its INT-HIST-001 in
bm-p7a's relay, now name only g8.5, the equation still undecided. The mutation variants keep their expected codes.
Records of genuine traffic with an error or a warning fell from 39 to 37, and records with an error are unchanged at 19. No specialist was called,
and nothing ran against a live provider or a deployment.

### 24.10 Integrated with the other argument-diagnosis work and the end-to-end fixes

This section's work was merged with the shared contract of named diagnostics, the evidence family, the argument family,
the channel work and the re-run review fixes, on top of the end-to-end detection fixes of section 21. Every fix of each
side is kept. Where two of them changed the same STEM reading, both readings are kept:

- **`_eq`** keeps the antilogarithm read as a concentration (section 21; forced SI reading, its label and detail), the
  affine readings and tolerance labels of the review fixes (section 22), and this section's unit companion, angle hint
  and degree-radian branch: `_readings(nodes, force="si" if scale_unit else None, affine=_affine_mode(ctx, nodes))`
  inside this section's general branch.
- **`_sol`** keeps the review's intent rule (a stated exactness makes a decimal root exact) and section 21's described
  roots (a value stated in prose for a described quantity is always read through its rounding interval):
  `exact_roots = [_root_is_exact(r, decimals=ctx.exact_intent) and not rel.described for r in roots]`.
- **The planner** (`stem/relations.py`) holds section 21's model, function and described-root methods beside this
  section's stated-operation, failed-comparison and scale readings; `plan_relations` takes the definitions, the reading
  and the answer text.
- **Check kinds**: `mod` (section 21) beside `op`, `sys`, `rnd` and the `u` companions; `_BUILDERS` holds every builder.

Two of the changes this section handed over are applied (24.5 and 24.8: the B17 bus line, per branch, and the linear
emphasis reading of `strip_markup`). A third came from the evidence family's security work: the STEM parser's unit
reader (`adapters/stem_specialist/parser.py`, `_units`) searched an unanchored accuracy-mark pattern from every start of
a line, so a STEM answer with 20,000 spaces in a sentence took 3.3 s to parse (about 3.6 s to deliver). `branches/generic_parser.accuracy_marked`
decides `_ACCURACY_MARK_RE.search(line) is not None` in one linear pass (computed from the right: whether the rest of
the line is a run of marks, then only the lead of a start); the generic parser's `_logical_lines` and the STEM `_units`
use it, and the same answer parses in about 0.06 s. It gave the pattern's answer on 300,000 random strings when written;
`tests/branches/test_accuracy_marks_linear.py` compares 60,000 and bounds four adversarial lines of 200,000 characters.

One test was rewritten to the merged rule, and it states a stricter assertion than before:
`tests/stem/test_e2e_run1_detection.py::test_a_step_and_its_roots_through_a_rational_power_are_proved_exactly`. Section
21 asserted a `stem-alg` and a `stem-sol` check for both answers. Under the root-set rule of section 22 (S5), a step from
the equation to one member of a stated set of two or more roots ("x = 2√2 or x = −2√2") is not checked on its own: the
`stem-sol` check substitutes each member exactly and, the full set being claimed, decides its completeness, which is the
step itself. The test now asserts, per answer, the `stem-sol` check and the check that proves the step (`stem-sol` for the
stated pair, `stem-alg` for the single `±` root), that every check holds, that each root's membership is exact, and, for
the pair, that completeness is decided. No error is allowed, as before.

Measured on the integrated tree: docs/ARGUMENT_DIAGNOSTICS.md, section 6.

### 24.11 Repair round 1 of the argument diagnosis

The review of the integrated tree re-ran the STEM checks on new probes (`tests/data/repair_round1_cases.json`, the t, u
and w cases) and on variants of earlier findings. Each change below is fixed at its cause, with a positive case and a
control (`tests/contract/test_repair_round1_cases.py`, `tests/stem/test_repair_round1_variants.py`):

- **Wrong formulas.** ST-REF-001 drops only pure coefficients (a small integer or a simple fraction); a decimal, a figure
  in scientific notation or a value equal to a stated quantity is a fitted constant with a unit, so a fitted law
  ("v = 1.5t", "F = 50x") names nothing. A result's dimension also follows from the last line of its chain and from the
  request's quantity for a substituted numeral, and ST-DIM-001 compares a law's dimension with its result's. The
  reference grew to 70 quantities (period, length, energy, work, weight, charge, heat, concentration, molar mass,
  magnification, BMI, a series' sum and term, ...) and 94 booklet laws, and ST-REF-002 names a law that has exactly the
  variables of the booklet laws for its quantity and differs from each as a function (interval enclosures of both sides
  at two sample points do not meet): the dropped ½ of E_k = mv², which keeps the dimension.
- **Units.** The traced reading of ST-UNIT-003 also accounts for numerals the request states with units (a volume in cm³
  used as dm³) and for numerals already in SI; a unitless binding (a magnification) is dimensionless as written; a binding
  in grams or minutes ("m = 500 g ... F = 500 × 2.0 = 1000 N") fails the unit companion. The substitution check's SI
  tolerance is scaled with the computed value (0.0005 µm was once read as 0.0005 m).
- **Extrapolation.** ST-RANGE-001 reads the model from a stated law or a binding near the evaluation, the input from a
  binding, a condition ("At t = 12 min") or the prose, and a series of years only from the request's data statements; a
  caveat under a negation is none.
- **Rounding.** The prose number reader glued numbers by the wrong token's spacing; "Since 0.05 is not less than 0.05" is
  read, so a rounded p-value that reverses the decision is ST-ROUND-001. A rounding labelled with the wrong precision
  ("4380 = 4400 (1 s.f.)") fails.
- **Symbol conflict.** ST-SCOPE-002 tells two objects apart by an ordinal ("the second trolley").
- **Working and steps.** A value binding ("x = 5.") is working for ST-WORK-001, and a check built from the request's own
  givens or target is not. ST-STEP-001 may take its first step from the request's one equation, and the dollar-delimited
  gap before a step is read from the right character. A root lost by dividing by x after "Dividing by x," fails its step.
- **Solution sets.** In Mathematics a root stated for a request that asks to solve the equation, or for all its values,
  solutions or roots, claims the full solution set ("Solve the equation." answered by "x² = 4^{1.5}, so x = 2√2" loses
  −2√2 and fails `stem-sol`), as a root after `⇒` or `∴` or on the line after its equation does. Bare values that continue a
  stated root in its statement are members of the set ("x = 0, 2 or −2", "x = 2 or 3", "x = 0, ±2"), and a set whose
  members are joined by "or" or "and" claims the full set, as "x = 2 or x = 3" does; so a set in that form is decided on
  every member it states, where its first member alone was decided before (a correct "x(x² − 4) = 0 ⇒ x = 0, 2 or −2"
  failed, and "x = 2 or 4" for x² − 5x + 6 = 0 passed). A step to such a set concludes the set, not its first value, so
  it is context of the set's check like a step to one member of a stated set (section 22, S5), whichever equation it is
  read from ("x(x² − 4) = 0, so x = 0 or x² = 4, giving x = 0, 2 or −2" failed as the step from x² = 4 to x = 0); a
  wrong member still fails the set's check. No full set is claimed when the set goes on with a value the
  reading does not take as a plain number ("x = 2√2 or −2√2", "x = 1.41 or −1.41 (3 s.f.)", "x = 3, 2 marks"): its read
  members are checked as stated roots only. None is claimed either when the statement calls the root one of several
  ("x = 3 is one solution"). A concluding word ("so", "hence") claims no full set by itself, written in prose or in LaTeX.
- **Givens.** ST-GIVEN-002 also names a given that lies outside the enclosure of the value the working computes for it
  from the other givens; ST-GIVEN-003 names a probability outside [0, 1], and events treated as mutually exclusive or
  independent against the request's own joint figures.
- **Readings that were false errors.** A comparison the answer calls false (", which is false") is no asserted
  comparison; space-grouped thousands beside a sign are read ("1 500 × 2 = 30" fails, "1 500 × 2 = 3 000" holds); a
  spaced AND dot ("A . B") is the whole product; a direction stated with scientific-notation figures is checked; a
  simplification of the request's own expression is no restatement of the request; condition items, binary literals and
  input words after a result cue are read as the statement reader means them.

The STEM front end reads a 400,000-character answer of list items in linear time, about 5 s when measured (the
README's "under two seconds" covers the adversarial inputs of `tests/stem/test_front_end_safety.py` only).

### 24.12 Repair round 2 of the argument diagnosis

The review of the repair round 1 tree found STEM misses and false errors on its probes and on a second blind hold-out.
The hold-out's cases were not read: each class below was reproduced on probes written for this round in the shape the
review names, fixed at its cause, and pinned with a positive case and a clean control (`tests/stem/test_repair_round2_stem.py`,
28 tests, `tests/stem/test_repair_round2_layouts.py`, 47 tests, and `tests/stem/test_repair_round2_classes.py`, 53 tests, which
delivers each class through the hub as a specialist's raw answer).

- **A rearrangement substituted with the task's values** (ADV2-02). "V = IR, so R = 6.0 / 0.50 = 12 Ω" was a false
  `stem_invalid_step`: the step's symbols had no values, so the step was checked for every value of them. The checks
  stage now binds a step's unbound symbols to the request's quantities of their reference dimension
  (`checks._request_step_bindings`, numbered siblings in request order, one quantity per symbol), so the step holds,
  while "R = 0.50 / 6.0" still fails.
- **A law whose head carries a subscript digit** (MISS-EXTRAP-SUBSCRIPT). A name declared with a numeral subscript
  ("CO₂") is one symbol, not C times O₂ (`parser`), so its law is a law and ST-RANGE-001 reads it.
- **Extrapolation by a stepped trend** (ADV2-08). An undecided law of one symbol (a symbolic power) is still a law for
  ST-RANGE-001, and arithmetic that repeats the request's data or binds a law's variable is evaluated as the trend
  ("each decade adds 15 ppm, so in 2100 ..."). A data series that writes its unit once ("at 10, 20 and 30 °C") is a
  series of three values (`document`, the request's shared-unit lists).
- **Rounding in its other natural shapes** (ADV2-06). A rounding stated in words after a chain's result ("which is 0.7 to
  one s.f.", "To 1 s.f. this is 0.7", "0.694 (0.69 to 2 d.p.)") is the chain's rounding (`relations._worded_roundings`);
  a comparison in symbols with the rounded value or the rounded chain's symbol ("so η ≥ 0.70"), and a comparison clause
  right after the rounded value ("≈ 0.7, which is not less than 0.70"), are `rnd` checks (`_compared_roundings`). A
  statement that the rounded value meets or misses a target is one too (`_target_roundings`): the clause up to the end of
  the sentence names a target (`TARGET_NOUNS`), says the value reaches it, goes beyond it or misses it (the reach, exceed
  and miss verbs, the passive "is met", "falls short of", a negation), and the target's value is the one value the clause
  states beside the noun or, when it states none, the one value the request states beside a target noun
  (`RequestReading.values` holds every value of the request's prose for this), with its bound ("at least", "more than",
  ...; none means at least). "78.96% ≈ 80%, which meets the target" for a target of at least 80% fails; "82.4% ≈ 82%, so
  the target of at least 80% is met" holds.
- **Word equations** (ADV2-07). A word equation is read as the formula it spells (`stem/word_formulas.py`: the reading
  view rewrites the reference quantities' names to their symbols, in the sciences), so a wrong one is ST-REF-002 and a
  correct one no ST-PARSE-001; "0.5 × m × v" is no magnification suffix (`spans._symbol_factor`).
- **A time converted inline** (ADV2-12). "E = Pt = 2000 W × (3.0 × 3600 s)": a two-factor law aligns with a product
  whose factor is bracketed (`nodes.align`), so the law's variable is bound and the value checked.
- **A condition named, not asserted** (FA-IFF-CS-MENTION). A relation after "condition", "test", "guard" and their kin
  is a named condition (context), unless the words right after it state its truth value ("(2 <= 1) fails"), which is
  checked as before (`document._names_a_condition`). In the arena's r7, "The passes test mid = 4, 1 and 2" is read so,
  and its info rebinding note (ST-SCOPE-001) goes.
- **A value after a preposition.** "in 2000 C = 340 + 1.75 × 20 = 375 ppm" and "At 60 °C R = …" were read as 2000
  coulombs, or 60 °C times R, equal to the result. A numeral right after a preposition, then only its unit, then a symbol
  directly before "=" says when or where the equation is evaluated: the run starts at the head (`spans._adverbial_value`,
  `adverbial_heads`).
- **Magnification.** A bare ratio of one kind of quantity given in two units (I = 40 mm, A = 20 µm, M = I/A = 40/20 = 2)
  gets the traced unit companion; the times sign of the magnification notation "= ×2" is read as the number it marks in
  the reading view, which `_truncated_operand` now reads, so it adjoins no operator.
- **Inverted formulas.** The ESS reference holds the Lincoln index (N = MC/R; N is the population size, a count), and the
  chemistry reference a dilution (c₁V₁ = c₂V₂, solved for each of its four symbols, with c₁, c₂ as ambiguous as c and V₁,
  V₂ as V), so "N = MR/C" and "c₂ = c₁V₂/V₁" are ST-REF-002 and the correct forms are clean.
- **A computation set out over lines** (own probes). "v = 8.4 / 2.0", then "v = 5.2 m/s" on the next line was read as a
  computation and a separate binding, so nothing checked the value. A chain that states a value for the symbol heading
  the previous chain, whose last operand is a computation that chain left unevaluated (closed, no value), continues it
  as "= 5.2 m/s" would (`relations._repeats_head`): same part, at most two statements on, equalities only, the same head
  symbol. The checks stage reads the gap between the two sides without the repeated head (`Relation.head_gap`), and the
  unit companion follows the chain across the lines. A law ("v = d/t") ends in symbols and is substituted as before.
- **The law on a line of its own** (holdout2 unit class). "E = ½kx²", then "E = ½ × 250 × 4.0² = 2000 J" with x given in
  cm: the traced companion counts the law's coefficients (½ and the exponent) as accounted for, as it already did when
  the law and the substitution share a chain, so the missing conversion is named.
- **A spaced product** (own probes). "E = ½ k x² = …" was cut to "E = ½": the working was never read and the request item
  looked unaddressed (INT-REQ-004), and "F = k x" was read as the law "F = k" (ST-REF-001). A single quantity letter of the
  profile's reference (or a name in scope, never "a" or "I") written with a space after a factor is a factor of the
  product when it carries a glued power or subscript, or when what follows continues the product (a relation sign, an
  operator, another such letter), and a bare letter may end the product at punctuation after another quantity letter
  (`spans._spaced_factor`). A bare letter after a number at the end ("E = 5 k.") and letters outside the reference stay
  unread.
- **Two objects told apart by a label** (holdout2 symbol-conflict class). The noun phrase of a binding keeps an object's
  label after its noun ("trolley A", "car 2") and, in chemistry, an element symbol; it is read in the binding's own clause
  (after punctuation that is no decimal point, a relation sign or a joining conjunction), and after the value when nothing
  before the symbol names a quantity ("Let m = 2.0 kg be the mass of trolley A", "m = 2.0 kg (trolley A)"), the value's
  own unit left out (`relations._phrase_words`). One symbol for two labelled trolleys is ST-SCOPE-002; m₁ and m₂ are
  clean.
- **Long answers** (parser-safety-11). Per-line work is bounded: an emphasis fast path, a no-marker path for the furniture
  reader, an index of mark ranges for prose numbers (it was one scan of every marker per statement), a first-character
  test before the relation-sign reader, and blanking and masking per line. A 400,000-character list answer now takes about
  3 to 3.5 s on this machine (it took about 4 s; 100,000 characters take about 1 s), still not under 2 s; the faster
  readers give exactly the old readings (`tests/translate/test_repair_round2_perf.py`, which pins readings, not times).

- **An equation after a condition** (own probes). "At t = 5.0 min T = 80 − 4 × 5.0 = 60 °C" read "min T" as one unit
  (minute tesla), a false arithmetic error, and in "At t = 2.0 s v = 3.0 m/s" the equation after the condition was never
  read. When a run is one binding opened by a preposition or "when", "if", a single letter (or a subscripted name) after
  its value and directly before "=" heads the equation the condition evaluates: the run ends before it and the next run
  starts at it (`spans._condition_head`). A compound unit of a plain value ("2.0 N m = 2.0 J") opens no condition and is
  read as before.

- **Givens that cannot all hold** (holdout2 contradictory-givens class; ST-GIVEN-004, `stem_contradictory_givens`). (a) The
  values the answer states for the symbols of one part fix every variable of a law of uniform motion (`GIVENS_LAWS`:
  v = u + at, s = ut + ½at², s = ½(u + v)t), the request or the answer says the motion is uniform, and the law fails
  beyond the rounding of the stated values and beyond 2% (`relations._overdetermined_givens`, outside Mathematics and
  Computer Science: the right side is enclosed over the corners of the stated values' rounding intervals in SI): "from rest at 2.0 m s⁻² for 5.0 s, reaching 12 m s⁻¹"
  (u + at is 10). A free fall ("dropped", "falls freely", "released from rest", "under gravity") is uniform motion too,
  unless the request or the answer says air resistance, drag or friction acts and does not say to neglect it
  (`_RESISTED_MOTION_RE`, `_RESISTANCE_NEGLECTED_RE`; own probes: "a stone is dropped from rest and falls for 2.0 s,
  reaching 25 m/s" with g = 9.8 m/s² is named, a skydiver "against air resistance" is not). (b) The request's counts of
  two sets in one sentence (a total, a count for each of exactly two named sets, one "both" and one "neither") do not
  add up, or "both" exceeds a set's count, and the answer computes with them (`_set_counts`: whole numbers compared
  exactly). Either is silent when the answer says the givens disagree ("inconsistent", "cannot all hold": the answer
  states the contradiction itself).
- **One symbol rebound with nothing saying which object each value is about** (holdout2 givens and symbol-conflict
  classes; `relations._unlabelled_rebindings`). Two bindings of one symbol in one part to different values, neither with a
  noun phrase, a scope phrase or a change marker before the second: (a) ST-GIVEN-002 when the request states the first
  value and not the second (`_request_states`: a request binding of the symbol, or a request quantity of the same
  dimension, equal within rounding) and a later substitution uses the second, written as a pair or inside an evaluation
  ("t = 3.0 s, and t = 2.0 s. a = (v − u)/t = 6.0 / 2.0" for a request that gives 3.0 s: `_uses_value`); (b)
  ST-SCOPE-002 when two symbols are each bound so twice, in parallel ("m = 0.50 kg and v = 4.0 m/s, and m = 0.20 kg and
  v = 6.0 m/s"), and one substitution takes one symbol from the first set and the other from the second
  (`_mixed_groups`; one finding per pair of symbols). Two values are different as written, in SI when both units read
  exactly (`relations._distinct`): "R = 10 Ω" and "R = 20 Ω" are two values even though a whole number with a trailing
  zero, read at one significant figure, would let them meet within rounding, and "t = 5.0 s" and "t = 5000 ms" are one.
  A substitution that keeps to one set of values, a symbol used twice in one substitution (a collision's m u + m u), and
  two times the request itself states are clean.
- **A model the request states, past the range it states** (holdout2 extrapolation class; ST-RANGE-001,
  `relations._request_law_ranges`). A law in the request ("the regression line s = 6.5h + 30", "the line A = 3.5N + 10")
  with the range of its input in words ("hours of practice h (from 1 to 8 hours)", "concentrations between 2 mg/l and 12
  mg/l"), and the answer's substitution of a value of that input outside the range with no caveat, in any STEM profile.
  A range belongs to the law's variable when it follows the variable's symbol within 40 characters, carries the unit the
  request states for it, or is the request's only range and the law's only variable.
- **A dated trend in Mathematics** (own probes; ST-RANGE-001, `_extrapolation`, `_dated_years`). Mathematics reads the
  years of a dated series as data: a request that dates two or more years with a time word ("in 2010", "from 2010 to
  2020", "between 2018 and 2021", "by 2020", or a year range) and a model evaluated at a year outside them ("estimate the
  population in 2060" from 2010 and 2020) is named; a year inside them and a stated caveat name nothing, and an amount of
  money ("1000 dollars") or the terms of a sequence ("2010, 2015, 2020, ...") are no dated years, so nothing is read from
  them. Its other series (a sequence's terms, a function's inputs) are still never data.
- **A mass or current given in a submultiple and put into a law unconverted** (own probes; ST-UNIT-003, traced). A
  substitution may introduce numbers for symbols bound nowhere else ("ΔEp = mgΔh = 250 × 9.8 × 2.0" with only g bound:
  m and Δh introduce 250 and 2.0); they are recorded as substitution bindings, not as the check's pairs, and are now
  traced too (`_unit_companion`, `introduced`), so 250 is read as the request's 250 g and the missing conversion is named,
  while "0.250 × 9.8 × 2.0" is clean. The same holds for "V = IR = 300 × 20" with 300 mA.
- **Pressure in the closed reference** (ADV2 probe; ST-REF-001, ST-REF-002). Physics pressure (p or P = F/A, in Pa) is
  in `QUANTITIES`, `FORMULAS` and `BOOKLET_LAWS`; as p is also momentum and P power, the quantity is fixed only by the
  result's unit or the request, so "P = F × A = 600 × 0.30 = 180 Pa" is a wrong formula, while "P = W/t = 5.0 W" and
  "p = mv = 6.0 kg m/s" are clean.
- **A rounded value said to satisfy the request's condition** (own probes; ST-ROUND-001, `_target_roundings`,
  `_request_condition`). Besides a target noun, the condition a request sets on a value is a target: a predicate made
  conditional ("The method is acceptable only if the mean titre is at least 24.45 cm³", "provided that", "as long as")
  with the one value later in that sentence and its bound. When the clause after the rounded value asserts the predicate
  or denies it ("so the method is acceptable", "so the bridge is not safe", "unsafe": a word sharing the predicate's first
  five letters, a negation within the four words before it or the prefix "un" denying it: `_predicate_said`), the `rnd`
  check asks whether the comparison it rests on keeps its truth with the value before the rounding. A request with two
  such conditions, or two values in the condition's sentence, plans nothing.
- **The unit of the value before the rounding** (own probes; `checks._rnd`). A chain that writes its unit or its per cent
  sign once, after the rounded value ("= 24.447 ≈ 24.45 cm³", "× 100 = 78.96 ≈ 79%"), has the value before the rounding
  in that unit too; it was read as a bare number in SI against the threshold in m³, so a near-threshold rounding met
  every target and a correct "≈ 24.4 cm³, so the target is not met" failed. The bare value now takes the rounded value's
  unit or per cent sign when it is within a tenth of the rounded value as written; a value of another scale ("= 0.7896 ≈
  79%", a conversion in the rounding step) keeps its own reading.
- **Two's complement and Boolean evaluation chains** (holdout2 Computer Science class). A 0-and-1 numeral that the
  request or the answer calls a two's complement number ("the 8-bit two's complement number 11010011") is read with its
  leading digit weighing −2ⁿ⁻¹, exactly (`relations._binary_literals`, `_TWOS_NAMED_RE`), so "11010011 = −128 + 64 + 16 +
  2 + 1 = −45" holds and "= −47" is an arithmetic slip; a Boolean chain "NOT (A AND B) = NOT (1 AND 0) = NOT 0 = 1" is
  read as one relation per pair of neighbouring expressions, as an arithmetic chain is (`boolean._chain_links`, at most
  16 links; it was refused whole as ST-PARSE-001), so a wrong link is named.

- **An item answered in notation** (own probes; `stem/hub_hooks.py`, `channel/bus.py`). "Calculate the pH" answered by
  "pH = −log₁₀[H⁺] = 2.60", "verify that NOT (A AND B) = (NOT A) OR (NOT B)" answered by evaluating both sides, and
  "Calculate Simpson's diversity index D = 1 − Σn(n − 1)/(N(N − 1))" answered by "D = 1 − 132/380 = 0.653" shared no
  topic word with their items and were INT-REQ-004 (unaddressed). The hook now finds a claim about the item when it gives
  a value to a reference quantity the item names in words (`named_quantity_symbols`: "the pH" is pH), to a symbol the
  item defines by a formula it states (`_formula_subjects`), or checks a Boolean relation for a Boolean item, and the
  channel lets that evidence stand in for the shared terms; an answer that does not address the item ("The solution is
  acidic because it contains hydrogen ions.") is still INT-REQ-004 (`tests/translate/test_repair_round2_readings.py`).

Left undecided by this round, each a miss and never a false alarm: a precision note inside a chain ("79.0% (3 s.f.) ≈
80%") ends the chain; a rounding to "the nearest 10%" is not read as a rounding.

### 24.13 Repair round 3 of the argument diagnosis

The review of the repair round 2 tree found STEM misses on its supplementary hold-out (V3-H2-STEM-MISSES), contradictory
givens over a reference relation and a rounding before a comparison written with the symbol (ADV3-09), a cancellation that
lost a root unnoticed (rerun-stem-soundness-11) and a unit companion charged on a percentage rounding (ADV3-03). Each is
fixed at its cause; the tests are `tests/stem/test_repair_round3_stem.py`, each class with its control, in wording of
their own.

- **A rewrite that is no identity** (ST-STEP-003, warning; `relations._false_rewrite`, `reference.difference_witness`). In
  a chain `A = B = C`, two neighbouring expressions of the unknown that hold the same unbound symbols, with a further link
  after them, are a rewrite step; the step is invalid when rational interval enclosures of the two sides at a sample point
  of the unknown do not meet ("log₁₀ x + log₁₀ 2 = log₁₀(x + 2) = 1"). The same witness serves the formula comparison
  (`reference.differs_as_function`). It is planned before the "a function of an unknown" coverage note, so the note
  stays for the relations the encodings cannot decide. Controls: "log₁₀(2x)", "(x + 3)² = x² + 6x + 9".
- **Givens against a definition law** (ST-GIVEN-004; `relations._overdetermined_givens`,
  `reference_data.DEFINITION_GIVENS_LAWS`). The answer's given ρ, V and m are read against ρ = m/V, with the laws'
  dimensions checked, and a uniform motion's givens against every motion law they fix (the uniform flag of the request or
  the answer); an integer written with trailing zeros ("2000 kg m⁻³") beside a given written with a decimal point is read to
  its last digit (±0.5), not to its first significant figure.
  Controls: consistent givens.
- **A rounding before a comparison written with the symbol** (ST-ROUND-001, the `rnd` check;
  `relations._symbol_prose_comparisons`). "R = 2.0 + 1.96 = 3.96 ≈ 4.0 Ω. R is not below 4.0 Ω, so the component fails"
  compares the rounded value through its symbol in the next sentence; the comparison is planned like the prose ones, so
  the value before the rounding (3.96) decides it. Control: the comparison read from the unrounded value.
- **A model the request states, outside its range, in any subject** (ST-RANGE-001; `branches/packs.request_model_extrapolation`).
  The core pack reads the request's fitted line and the range of its input in words ("For nine storms with rainfall
  totals between 5 mm and 35 mm ... Q = 2.5R + 6") through the STEM document of the answer, so a Geography answer that
  substitutes 120 mm is named. Control: an estimate inside the range.
- **Missing working** (ST-WORK-001; `relations._working`, `reference_data.WORKING_CUES`). Computer Science is no longer
  exempt when the request asks for the method in words ("showing your method"); a "Show that" answered with the result
  alone, whose values are all the request's numerals, is missing working. Controls: the worked conversion, the request
  with no method asked, the derivative and second-derivative test written.
- **A cancellation is a division** (ST-STEP-002 and the root check). "Cancelling x," "cancelling a factor of x" divide
  both sides by the unknown, as "Dividing by x" does, so the root line after the equation claims the full set and a lost
  root fails it. Control: the factorised working.
- **One quantity written once** (ADV3-03; `reference.unit_written_once`, shared by `checks._rnd` and
  `relations._unit_companion`). A percentage written bare and rounded with its sign ("131 / 250 × 100 = 52.4 ≈ 52%") is
  one quantity in one unit, so no unit companion charges the bare 52.4 against 0.52. A rounding to another value is still
  an arithmetic error.

Left by this round (each documented in `docs/ARGUMENT_DIAGNOSTICS.md`, section 7): the ST-UNDEC-001 coverage notes on
correct work with a derivative, a logarithm or a Σ stay (they state what was not checked).

### 24.14 Repair round 4 of the argument diagnosis

The review of the repair round 3 tree found a missing conversion to the absolute temperature (ADV4-01), times given only in
the request substituted unconverted (ADV4-02), a wrong area formula and a correct period over values the request gives
(ADV4-11), a false identity checked only under a cue word (rerun-stem-soundness-12), and STEM readings outside the STEM
pack (rerun-stem-precision-11, rerun-parser-safety-13, ADV4-12). Each is fixed at its cause; the tests are
`tests/stem/test_repair_round4_stem.py` and the files named in each item, each class with its control, in wording of
their own.

- **The absolute temperature** (ADV4-01; `reference_data.ABSOLUTE_TEMPERATURE_LAWS`,
  `relations.applies_absolute_temperature_law`, `relations._kelvin_binding`, wrapper `KELVIN_READING`). In a law whose
  T is the thermodynamic temperature (pV = nRT and the combined gas laws, ΔG = ΔH − TΔS, E = (3/2)kT, the
  Stefan-Boltzmann and Wien laws: a law of the working is one of these when its symbols, subscripts aside, are among one
  row's and include T), a temperature written in °C or °F is read in kelvin, so "V₂ = V₁ × T₂/T₁ = 3.0 × 117/17" for 17 °C
  and 117 °C fails its unit check (INT-SUBJ-004, `stem_unit_error`). In any other law a temperature on an offset scale is
  left unread (it may be a difference). Control: the same law with the temperatures in kelvin.
- **A quantity already written in SI** (ADV4-02; `relations._si_form_binding`). A bare numeral that is the request's
  quantity converted to SI ("240 000" for "240 kJ", "2000" for "2.0 kW") is accounted for as that binding, so the other
  numerals of the working are read with the request's units: a time given in minutes or hours and substituted as written
  into P = E/t or E = Pt fails its unit check. Control: the working with the time in seconds.
- **Values the request gives** (ADV4-11; the substitutions of `relations._Planner`, `nodes._rounded_constant`). A bare numeral
  substituted for a symbol the request states with an SI unit ("radius 5.0 m", "a mass of 0.20 kg") carries the request's
  unit, so the law's dimension is read and A = 2πr for an area is named (ST-DIM-001); π or e written as a rounded decimal
  of three or more significant figures ("3.14", "2.718") aligns with the symbol, so a correct T = 2π√(m/k) raises no
  ST-UNDEC-002 (a false alarm on the base tip too). Controls: A = πr²; the correct period. The inverted period is still
  named (ST-REF-001).
- **An identity under any request** (rerun-stem-soundness-12; `relations._identity_shape`, `_factorised`,
  `_exact_degree`, `_cued_identity(shape_only=True)`). An equation of polynomial sides whose shape is an expansion or a
  factorisation ("(p + q)² = p² + q²", "y² − 16 = (y − 4)(y − 4)") is checked as an identity whatever the request says,
  with its failure a warning (the reading is inferred); a request that asks for values or solves the equation, and an
  equation the answer solves later, are no identity claim; a rewrite that keeps the previous equation's right side is a
  step. Controls: the true identities.
- **Answer words outside the STEM pack** (rerun-stem-precision-11; `channel/bus.py`, `_worked_calculations`). A line of
  worked arithmetic is answer proper in Economics, Business Management, Geography and Psychology too, in every notation, so
  such an answer is not "no answer" (INT-REQ-012). Controls: a note alone, a quoted calculation
  (`tests/channel/test_repair_round4_answer_words.py`).
- **The general figure reader** (rerun-parser-safety-13; `branches/quant.py`). Space-grouped figures and a scale word
  against scientific notation are read whole, and a figure with a scale word is compared with a whole figure of the same
  noun phrase ("2.5 million tonnes" against "1,800,000 tonnes", `_same_noun_phrase`, `_sci_pair_number`); an unknown unit
  word still makes the pair incomparable (`tests/branches/test_repair_round4_quant.py`).
- **A chained trend read link by link** (ADV4-12; `quant._CONT_ADVERB`, `_unread_figure_between`, `_Patterns.figure`).
  A continuation with a manner adverb ("then rose sharply to 11.4%") is read in both readings (the SI patterns are
  composed as the general ones), and a continuation is never chained across an unread level of its own unit and currency
  (a year, a stated change of the link before, and a figure of another unit do not break the chain). A figure the answer
  credits to a named data table for a year that the table states otherwise is CORE-SRC-007
  (`tests/branches/test_repair_round4_table_figures.py`).

### 24.15 Repair round 5 of the argument diagnosis

The review of the repair round 4 tree found a unit given only in the request missed in the specific-heat law (ADV5-03),
contradictory givens written inline (ADV5-04), conclusions drawn from rounded values in common shapes (ADV5-05), formulas
written as adjacent letters (ADV5-06), one symbol for two quantities (ADV5-07), missing-working warnings on reasoned
proofs (ADV5-10), an extrapolation hidden by a unit homograph (ADV5-16), a count stated in a sentence read as no value
(ADV5-18) and a '±' step inside a chain charged as an error (rerun-stem-soundness-10). Each is fixed at its cause; the
tests are `tests/stem/test_repair_round5_stem.py`, each class with its control, in wording of their own, and each positive
case fails on the tree before the round.

- **A unit given only in the request** (ADV5-03; `relations._unit_companion`, `_request_difference_for`, `_written_change`).
  The request's unit of a quantity ("c = 900 J kg⁻¹ K⁻¹", "a 300 g block") is traced through the working's differences
  (a Δ the request's figures give) and through the values the working computes, so "Q = mcΔT = 300 × 900 × 20" with the
  mass in grams fails its unit check (ST-UNIT-003, `stem_unit_error`). Control: the mass in kilograms.
- **Inline givens** (ADV5-04; `relations._inline_givens`). A value with its unit written inside a substitution ("F = ma =
  4.0 kg × 3.0 m s⁻²") is a given of the working: when it contradicts the value the request states for the same quantity it
  is a contradictory given (`stem_contradictory_givens`), as a "Given" line was. The request's own value written inline is
  clean.
- **Rounding that decides** (ADV5-05; `relations._target_roundings`, `_CONDITION_RE`, `_target_verb`). A conclusion drawn
  from a rounded value in the common shapes ("20.4 kN ≈ 20 kN, so the beam is safe" against "at most 20 kN"; "30 m s⁻¹ to 2
  s.f., so it reached the limit"; a percentage rounded onto a pass mark) is ST-ROUND-001: a rounding stated in words after
  the rounded value ("to 2 s.f.") ends no clause, a value "at the limit" reaches it, and a condition the request states
  with "only if", "provided", "as long as", or a copula with "if" or "when" ("A beam is safe when the load on it is at most
  20 kN") is a target. Control: the conclusion drawn from the unrounded value.
- **Adjacent letters** (ADV5-06; `spans._quantity_run`, `parser._juxtaposable`, `_quantity_letters`, `_NUMBER_GLYPHS`). Letters
  written together or spaced ("mv", "½ m v", "2πrh") that are each a quantity of the profile are a product, never one
  unknown symbol, so "E_k = ½mv" is checked against the reference law (`stem_wrong_formula`); the Mathematics profile gains
  the volume, area, radius and height quantities and the booklet's volume and area laws. Control: ½mv².
- **One symbol, two quantities** (ADV5-07; `relations._dimension_rebindings`). A symbol bound to a value in one dimension
  (P = 400 Pa) and later to another (P = 300 W), then substituted in the first sense, is ST-SCOPE-002
  (`stem_symbol_conflict`). Control: two symbols kept apart (p and P).
- **Reasoned proofs** (ADV5-10; `relations._PROPERTY_SHOW_RE`, `_REASONED_RE`). A "show that" request about a property
  (prime, even, irrational, ...) answered with a reason, and a yes/no "calculate whether" answered with the request's own
  figures, is no missing working; a bare property ("14 is even.") or a bare result is still ST-WORK-001, as the round-3 pin
  requires.
- **Unit homographs** (ADV5-16; `spans._UNIT_HOMOGRAPHS`). A unit symbol that also writes a short English word ("as", "at",
  "am", "us", "an", "in", "das") never continues a unit already begun ("mol dm⁻³ s⁻¹ at 5.0 ..."), so a prediction far
  beyond the measured range is read and named (ST-RANGE-001, `stem_extrapolation`); "5 as" alone is still an attosecond
  (`tests/stem/test_units.py`). Control: an interpolation.
- **A count stated in a sentence** (ADV5-18; `checks._request_count`). "A sample contains 600 undecayed nuclei" gives N₀ its
  value, so a correct N = N₀ × (½)³ = 600 / 8 raises no ST-UNDEC-002. Control: a wrong count is still charged.
- **'±' inside a chain** (rerun-stem-soundness-10; `relations._roots_candidate`, `_root_set_members`, `checks._sol`). An
  equation with '±' ("x + 2 = ±3") is read as two equations, and a root set derived from it is checked against both, so
  "(x + 2)² = 9 ⇒ x + 2 = ±3 ⇒ x = 1 or x = −5" holds. Control: a wrong root after the '±' step is charged.

### 24.16 Close round 1 of the argument diagnosis

The regression review of the repair round 5 tree against the committed base found two STEM readings worse than the base on
correct work; each is narrowed at its cause (`docs/ARGUMENT_DIAGNOSTICS.md`, sections 3.4 and 12). Tests:
`tests/stem/test_close1_stem.py`, each shape with its control, in wording of their own; each positive case fails on the tree
before the round.

- **A magnitude after its own signed chain** (ADV6-02; `relations._Planner._results`). The end-to-end B2 fix lets a prose
  value restate a chain of its own statement; a value of the other sign than that chain ("a = (0 − 16)/4.0 = −4.0 m s⁻², so
  the deceleration is 4.0 m s⁻²"; "= −8.0 J, so friction does 8.0 J of work against the motion") states the magnitude in the
  words of a direction and is no restatement, so no `res` check is planned for it. Control: a restatement of the same sign
  is checked, and a wrong one ("so the acceleration is −5.0 m s⁻²") fails.
- **The model's evaluation point** (ADV6-07; `relations._INPUT_BEFORE_RE`, `_RATE_AFTER_RE`). A value in prose is where a
  model is evaluated (ST-RANGE-001) only when an input cue stands before it ("at", "for", "when", "if", "with", with at most
  a determiner and three words between) and no rate or step follows it ("per year", "a year", "/", "each", "every"): a rate
  in an interpolation ("rises by 0.05 °C per year") and a sum's result restated in prose ("13.4 A, which is 13 A to 2 s.f.")
  are no evaluation points. Control: "At 90 °C, rate = 0.30 × 90 = 27 units" beyond data at 10 to 30 °C is still named.
  Given up: an evaluation written as an attribute ("a 40 N load ...") is not read; the request's series that takes a year
  into a unit's range only widens the range (misses, never a false alarm) and is unchanged.

### 24.17 Close round 2 of the argument diagnosis

The regression review of the close round 1 tree against the committed base found one STEM reading worse than the base
(`docs/ARGUMENT_DIAGNOSTICS.md`, sections 3.4, 7 and 13). Test: `tests/stem/test_close2_boolean_dot.py`, in wording of its
own; its positive case fails on the tree before the round.

- **The AND dot and Boolean constants** (DIFF-04; `lexer.writes_constant_dot`, `lexer.lex`, `checks._truncated_operand`).
  The AND-dot reading of stem-soundness-4 reads a full stop between two operands as AND, but the lexer reads a dot before a
  digit as a decimal point, so in a step written with a constant ("Since A.0 = A, we get A.B + A.0 = A.B + A = A") the
  expression was read only in part and the guard against a relation glued to a dot between letters withheld what was
  left: a wrong step went unchecked, where the committed base, whose full stops are full stops, charged it (INT-SUBJ-001).
  An answer that writes a Boolean constant with the AND dot (an operand of one or two capitals that ends no longer word, or
  a closing bracket, glued by a full stop to a lone 0 or 1) is now read without the AND dot and without that guard, as
  before both readings; every other answer keeps the AND dot. Control: a correct absorption written with the AND dot ("A.B
  + A = A") stays checked and clean, and the correct step "Since A.0 = 0, we get A.B + A.0 = A.B + 0 = A.B" raises no
  error. Given up: the base's reading of
  those full stops also charges a correct step written with a constant and the AND dot ("Since A.1 = A, we get A.B + A.1 =
  A.B + A = A"), as on the base; the constant identity itself is checked in neither tree.
