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
| `datatables.py` | the pipe tables of the texts supplied with a request (rule `table-data`, section 21) | core |
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
   shared JSON rule.

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
    of exactly three, one kind of separator throughout (section 33).
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
(section 33). So is an integer power beyond 12, up to 1000, of a closed base with no unit
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
  rounding). A substituted value passes if it matches any binding of that symbol, so part (b)
  reusing part (a)'s letter is never flagged.
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
| an equality with an application of an exponential model (the model's letter glued to its bracket) | `P(t + 1) = P₀e^(k(t + 1))` after `P = P₀e^(kt)` | `stem-mod` (section 33, item 5) |
| answer `Given:` binding against a request binding of the same symbol, or a request quantity of the same dimension; since STEM repair 2 (section 22) also the request's percentages, its numbers written with the same word, or the number a bare Given equals (rule `given-kinds`), and a supplied table's cell a Given names | `Given: v = 20 m s⁻¹` | `stem-giv` |
| final value against a show-that target in the request | "Show that n ≈ 2.0 mol" | `stem-tgt` |
| chemical equation | `2H₂ + O₂ → 2H₂O` | `stem-chem` |
| Boolean equivalence | `¬(A ∧ B) = ¬A ∨ ¬B` | `stem-bool` |
| truth-table block | header `A B A∧B` | `stem-tt` |
| based numerals | `FF₁₆ = 255` | `stem-base` |
| a relation whose endpoints contain Unsupported | `f′(x) = 3x + 2` | ST-UNDEC-001 (reason) |
| a numeric relation whose operands include a symbol with no binding and no admissible booklet reading | `E = hf = 3.3e-19` with f unbound | ST-UNDEC-002 |

A bare value binding with no relation stated (`The speed is 15 m/s.`, `m = 2.0 kg`) is a
binding, not a check. That keeps the existing Physics fixtures free of new findings. An order
chain is read (`T₁ = 300 K > T₂ = 250 K`), a factorisation inside a chain is checked as an
identity, a ratio equality `a:b = c:d` is compared by cross products, and a function or
derivative evaluated at a point is checked against the stated formula when one is recorded.
An evaluation of a function at a value (`f(2) = …`, and `N(15) = …` for a letter the text defines
as a function, `N(t) = …` or a model; section 33, item 5) is no step from the preceding line, and a
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
  the integer trailing-zero rule: the trailing zeros of an integer written without a point count
  only up to the smallest significant-figure count of the expression's measured operands, and
  none count for a value set against a value with no operands (a conversion's or a
  restatement's two values: 600 gives 50).
- **R2 Relative slack τ.**
  - `=` with any measured operand (written with a decimal point, in scientific notation, or
    with a unit) or a decimal S: 1/100. This covers constants written to fewer digits than were
    used (9.8 against 9.81 is 0.1 %; 3.00 × 10⁸ against 2.998 × 10⁸ is 0.07 %). It stays well
    below the error classes this design must catch (a wrong formula, substitution, digit or
    power of ten, typically 5 % or more).
  - `≈`, `≃` or `~`, or `=` after "approximately", "approx.", "about", "roughly", "estimate",
    "around" or "nearly": 1/20, whatever the check (a conversion or a comparison written `≈`
    included: `tolerance.tau_for`), but a restated result: R8 bands it with τ = 0, the
    approximation word before the restated value naming its rounding (the restatement check
    has always applied this; R2 states it since STEM repair 12, section 32).
  - **Exact mode** (every operand and S exact, and `=`): τ = 0 and h = 0. So `7/3 = 2` fails,
    while `√2 = 1.41` (S is a decimal) passes under R1.
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
  (1/20 when the conversion is marked approximate). The factors are exact, so the only slack is
  the half-widths of the two written values, `|C − S| ≤ h(S) + h(C)` in SI. Unknown unit atoms
  that are the same on both sides cancel; otherwise an unknown unit is checked as written only,
  at warning severity.
- **R6 Comparisons** (`<`, `≤`, `>`, `≥`, `≠`) between written values are exact, with no slack,
  as in quant's series checks.
- **R7 Substitution fidelity.** A substituted numeral w matches a binding b iff `|w − b| ≤ h(b) +
  h(w)`, in b's written unit or in SI. The two readings are a disjunction, so 2500 and 2.5
  both match 2.5 km. τ = 0.
- **R8 Restated result.** A prose value S′ matches the chain's final value S iff `|S − S′| ≤
  h(S) + h(S′)`, in SI, with τ = 0. A rounding the prose states for S′ ("To the nearest whole
  number, the decrease is 61%", "60%, to 2 s.f.": rule `rounding-cue`, section 21) gives h(S′):
  it says which trailing zeros of a whole number count (60 to two significant figures is 60 ±
  1/2, to one 60 ± 5), never less than half a unit in S′'s last written digit.
- **R9 Prose relations** (per cent, fold, share and total) keep quant's `TOLERANCE_RULE`: 5 %
  and the 0.5-point floor. In SI reading the band is made sign-aware (section 12). Those
  statements are approximate by nature; equations are precise statements. A value the prose
  takes from a table supplied with the request (rule `table-data`, section 21) matches the
  table's cells, or the difference of two rows, taken as written: `|S − D| ≤ h(S)`.
- **R10 Roots.** A stated decimal root r of a polynomial equation passes iff a real root lies
  in `[r − h(r), r + h(r)]` (Form S). An exact root passes iff it satisfies the equation exactly
  (linear substitution, D1).
- **R11 Central value** (rule `central-value`, STEM repair 3, section 23). A stated value written
  with its absolute uncertainty, `S ± u` ("586 − 20 = 566 ± 12"), is set against C at its central
  value S under R1 to R4: u never widens h, and this rule does not check u itself (rule
  `stated-uncertainty`, STEM repair 4, section 24, sets u against the rule the answer states for
  it). The band had been added to h, so a slip within it (`586 − 20 = 556 ± 12`) passed.
- **R12 Operand precision** (rule `operand-precision`, STEM repair 4, section 24). For "=" in written
  arithmetic whose computed side is an expression of written numerals only (no carried result,
  constant, symbol or function value), τ is twice the largest relative change the rounding of
  those numerals can make to C, rounded up to a millionth, when that is below 1/100
  (`4000 × 1.036³ = 4467.74` fails at τ = 1449/500000); a stated value that is a whole number
  ending in zero, written without a point, keeps 1/100. The check's statement gives the τ used;
  the short form's 1/100 is the most τ a check uses for "=". A numeral that writes a value the
  request states is given data, taken as written (R3), so it is exact, never rounded: a per cent
  the request states gives its decimal and the factors 1 ± the decimal (3.6% gives 0.036, 1.036 and
  0.964), and `4000(1.036)^{12} = 6141.73` fails at τ = 0 (STEM repair 10, section 30); a stated
  side that is itself an expression of written numerals adds their rounding to the bound.
- **R13 Exact carry of exact working** (rule `exact-carry`, section 24). A numeral that carries an
  earlier result of exact working ("T = ln 2 ÷ ((ln 2)/8) = 8") is exact, with no interval under R3.

**The observed case.** C = 5, S = 6.0, h = 0.05, τ = 1/100, and |5 − 6| = 1 > 0.05 + 0.05, so
the check fails. Under quant's 5 % rule it would have passed anything from 4.76 to 5.26.

**Short form** (`tolerance.SHORT_RULE`, the `[rule]` suffix of every description, 300
characters or fewer): "STEM tolerance: |C − S| ≤ h + τ·|C|; h: half a unit in S's last digit
(integer trailing zeros only to the operands' s.f.), plus C's own h if C is a stated value; τ:
1/20 for ≈/about, any check; else 1/100 for = in arithmetic, 0 for conversions, comparisons,
substitutions, restatements, exact work." The full rule is `tolerance.STEM_TOLERANCE_RULE`.
(STEM repair 1, section 21: the earlier short form said "h is half a unit in S's last digit" and
"0 for conversions" while the checks applied R1's trailing-zero rule, R2's precedence of `≈`
over every check kind and R4's second half-width; the pack's statement of the rule is tested
against the code that applies it.)

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
  is metre second, and `Nm` and `N m` are newton metre. A Latin prefix written before a Greek
  unit symbol (`kΩ`, `MΩ`, `mΩ`, `GΩ`, `μΩ`, glued to its number or apart) is one prefixed unit
  (`units.GREEK_PREFIXABLE`, `prefixed_greek_unit`): the lexer reads the Greek letter as a token
  of its own, so before STEM repair 1 `2.4 Ω = 0.0024 kΩ` was read `2.4 Ω = 0.0024` and failed.
- **Counts.** `count` (`counts`, `counts min⁻¹`, `counts s⁻¹`) is a count, dimensionless.
- **Unit expressions.** Space, `·`, `*`, `/`, and exponents `⁻²`, `^-2`, `^{-2}`, `**-2`. For
  example `m s⁻²`, `m/s/s`, `J mol⁻¹ K⁻¹`, `mol dm⁻³`, `kg·m/s`, `kJ mol⁻¹`. After a number, an
  exponent written in ASCII and glued to its atom is read too: a hyphen-minus or plus and one digit
  (`m s-1`, `mol dm-3`, `J kg-1 K-1`), one digit 2 to 9 after an atom of two or more letters (`cm3`,
  `mol2 dm-6`) or after a slash (`m/s2`, `kg/m3`); never more digits (`300 K-273`), a spaced sign, a
  sign followed by an atom of the same dimension (`5 m-3 m`), or a one-letter atom's digit right after
  the number (`2 m2`, `H2`), which keep their reading (section 33, item 6).
- **Factors.** SI conversion factors are exact `Fraction`s. Where no exact rational factor
  exists (the degree, which is π/180 rad, and the parsec) the factor is `None` and the unit still
  has a dimension. The affine offset (273.15 for °C, 459.67 for °F) is applied only in explicit
  °C/K conversion checks. It is never applied to a Δ-prefixed symbol, or to a quantity the
  sentence calls a change, difference, rise or fall. Inside a compound unit (`J kg⁻¹ °C⁻¹`) °C
  is a temperature interval, like K.
- **Not in the table.** `yr` (a known gap: ST-UNIT-001, see docs/STEM_RESULTS.md) and any unit
  not listed above.

### 6.2 Where a unit is read

A unit is read only after a number, after a closing group that contains a number, or inside
`\text{}` or `\mathrm{}`. Elsewhere a letter is a symbol. After a number, the English words
`as`, `am` and `at` written apart are no units (`units.ENGLISH_NOT_UNITS`: "5 as before", "10 am",
"22 at E"); the atoms attosecond, attometre and attotonne stay in the table.

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
  SI only**. So `2.0 km / 4.0 s = 0.5 m s⁻¹` fails, as it should.
- Some operands are bare numbers and some carry units: **disjunction {as written, SI}**. So
  `v = 72 km h⁻¹ ÷ 3.6 = 20 m s⁻¹` (3.6 is a bare factor) and `4.5/6.0 × 100 = 75 %` both pass.
- No operand carries a unit: compare as written, and S is read both as its number and in SI
  (`20 × 25 = 0.5 km` passes in SI).
- One exception: a lone power of ten with no unit (`10^(−8.2)`, `10^(−7)`) set against a value in a
  unit of concentration is the antilogarithm of a concentration scale, the concentration in mol dm⁻³
  (the unit pH, pOH, pKa and pKb are defined in), compared in SI only. Read as a bare number in SI it
  would match a stated value 10³ times too small, the factor an exponent 3 too small reproduces
  (section 33, item 1).
- An unknown unit word: ST-UNIT-001 warning. The relation is checked as written only, with
  `failure_severity="warning"`.

### 6.5 Dimension checks (deterministic integer-vector arithmetic; warnings only)

- **ST-DIM-001.** The two sides of a stated relation have different dimensions, where every
  operand's unit is read unambiguously or is a bound symbol's unit. Example: `a = (v − u)/t =
  5.0 m s⁻¹` with v in m s⁻¹ and t in s.
- **ST-DIM-002.** A sum or difference of terms with different dimensions.
- Bare numbers are "unitless as written", not dimensionless. When they leave the dimension of
  a side unknown, rule `bare-factor` (STEM repair 1, `relations.bare_factor_dimensions`) reads
  each one as the dimensions the answer gives it: the symbol it was substituted for, an equal
  value the answer or the request states with a unit, the data-booklet constant it matches, or
  else a pure factor. ST-DIM-001 when no such reading makes the two sides agree:
  `λ = 0.693 × 8.0 h = 5.5 h⁻¹`, `x = 2.0 s × 3.0 = 6.0 m`, `f = 1 / 2.0 s = 0.50 s`. A bare factor a
  stated value or a constant explains raises nothing (`v = 72 km h⁻¹ ÷ 3.6 = 20 m s⁻¹`,
  `F = 2.0 kg × 9.8 = 19.6 N`, `v = 3.0 m s⁻¹. x = 2.0 s × 3.0 = 6.0 m`).
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
  decided exactly when its value is rational, else through an enclosure, section 33), and integer
  powers beyond 12 of anything but a closed value with no unit. A power of e or of a positive rational
  with an exponent in symbols is read only inside a model evaluation (`stem-mod`, section 33, item 5),
  through positive variables that can refute a link but never prove it for every value.
- A function of an unknown (an exponential model applied to an argument is the one reading, `stem-mod`;
  no algebra step is read over an application of a letter the text defines as a function, section 33,
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
| `stem-eq-N` (`stem_arithmetic`) | a numeric link `E = S` (and `≈`); since STEM repair 2 (section 22) also integer remainders and quotients (`mod`, `div`, `//`, `%` in Computer Science, a stated remainder, a congruence), encoded with the IR's `mod` and `idiv` under `to_real` | E: ENTAILED; S: SATISFIABLE | linear unless surds or two interval operands are multiplied | error; warning when a D3b booklet value was used or a unit was unknown |
| `stem-sub-N` (`stem_substitution`) | substituted numerals against the symbols' bindings (R7). When the symbolic and numeric sides have the same tree shape, each aligned symbol is checked (a value written in another order of the same product or sum also matches, by bounded injective matching); otherwise, if every symbol is bound, the symbolic side under its bindings is checked against the numeric side (Form S over the binding intervals). A symbol with no binding takes a D3b booklet reading admitted by a dimension check, or the relation is ST-UNDEC-002 | E (pairs); E or S (evaluation) | as needed | error; warning when a D3b booklet value was used or a unit was unknown |
| `stem-alg-N` (`stem_algebra`) | the next relation follows from the preceding one, plus scope bindings of the symbols involved, plus at most 8 recorded formulas mentioning them, plus side conditions: divisors ≠ 0; a principal (non-negative) root in sciences profiles | E: ENTAILED | nonlinear when needed | error when the step is a pure manipulation (its symbols are a subset of the premise's symbols, bound symbols and included formulas); warning when it brings in unrelated symbols (an unstated law may be at work) |
| `stem-sol-N` (`stem_solution`) | membership: each stated root satisfies the equation (exact: linear substitution; decimal: R10). Completeness: the equation entails the disjunction of the stated roots, built only when the statement claims the full set, the parameters are exact and neither the statement nor the request restricts the domain ("positive", "x > 0", "length", "time", "reject", ...). A root may also be a decimal the answer states in prose for the quantity it named by the symbol ("Let $M$ be the monthly payment" … "Her monthly payment is €352.19"; section 33, item 4): membership only, over its rounding interval widened by τ = 1/100 | E; S for decimal roots | as needed (membership of an exact root is linear; completeness is nonlinear) | error |
| `stem-mod-N` (`stem_model`) | an equality with an application of an exponential model, the model's expression at the written argument against the other side: some value of the variables (the model's variable, every symbol with no stated value) and of the stated symbols within their stated values satisfies it, every power of an exponent in symbols read through positive variables (section 33, item 5) | S: SATISFIABLE (UNSATISFIABLE: no value satisfies the link) | nonlinear | error |
| `stem-cnv-N` (`stem_conversion`) | an explicit unit conversion (R5) | E | linear | error; warning when a unit was unknown |
| `stem-cmp-N` (`stem_comparison`) | a stated order or inequality between values (R6); bound symbols with several values pass when some admissible values satisfy it; also inequality-solving steps, checked as `alg` | E (or S) | as needed | error |
| `stem-res-N` (`stem_result`) | a prose restatement against the chain's final value (R8); since STEM repair 2 also a value given to a symbol after "so" right after a chain (rule `restated-binding`, at warning severity) | E | linear | error; warning when a unit was unknown or the restatement is a reading |
| `stem-giv-N` (`stem_given`) | an answer's `Given:` value against the request's binding of that symbol, or a request quantity of the same dimension; since STEM repair 2 (section 22) also against the request's values of its kind (rule `given-kinds`), a prose value against the request quantity its words name (rule `named-given`), and a value a line of working takes from a supplied table against the rows named (rule `table-operands`) | E | linear | warning (symbol identity across texts, and which value or row is meant, are readings) |
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
s2.4] [<short rule>] <form; policy; readings; details>`, at most 1,200 characters. Descriptions
name readings, factored exponents, supplied constants and side conditions. `StemPack` rewrites
the statement ids in a description to the report's own claim ids.

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

The STEM pack itself emits **no error-severity structural finding** about the answer. Every STEM error comes
from an engine result. The one error the pack adds is the hub's PACK-INTERNAL-001, when an internal failure leaves a
report with no STEM check at all (the front end emptied the document, or the pack raised): its checks are missing, and
the receipt carries an error so they are never read as passed (round-7 hand-off, parser-safety-1).

| Code | Severity | Decided by | Meaning |
| --- | --- | --- | --- |
| INT-SUBJ-001 | error | engine | a check of the report's own STEM statement does not hold, and it rested only on what the report or request states plus exact encoding devices (existing code; now carries `claim_ids`; for a STEM check the message gives the counterexample's computed value `c` and stated value `r`) |
| INT-SUBJ-002 | warning | engine | such a check is undecided: UNKNOWN, TIMEOUT, UNSUPPORTED, INVALID_FORMALIZATION, INTERNAL_ERROR, a vacuous result (E108), or INCONSISTENT_PREMISES on a check with `inconsistent_is_failure=False`; also (deterministic) an unknown policy name, an exception while deciding the check, or the report's STEM check budget (8 s) spent (existing code; now carries `claim_ids`) |
| INT-SUBJ-003 | error | deterministic | an error-severity pack finding, escalated (existing; STEM never produces one) |
| INT-SUBJ-004 | warning | engine | NEW: a check that relied on a reading the report did not state does not hold: a booklet value for an unstated symbol, symbol identity across request and answer, a show-that target, a step bringing in unrelated symbols, or an unknown unit |
| BR-INTERNAL-001 | warning | deterministic | NEW (`SubjectBranch.run_packs`): pack `<name>` failed internally (`<type>`) during `<checks or formal checks>`; its findings are missing from this receipt, and the router must not treat the pack as passed |
| ST-PARSE-001 | warning | deterministic | a math span uses notation outside the grammar (named: unknown LaTeX command, unbalanced group, a symbolic power); its relations are not checked. STEM repair 2 (section 22): also a relation written partly in words (rule `fragment`), a relation sign between maths that no span reads (rule `unread-relation`), a quotient and remainder or a congruence in another shape, and a Given that may be written with a thousands space |
| ST-PARSE-002 | warning | deterministic | an expression has more than 2 readings (or a check more than 4): implicit multiplication or unit/symbol ambiguity; not checked |
| ST-UNDEC-001 | warning | deterministic | a recognised relation outside the encodings (calculus, limits, Σ, vectors, matrices, complex numbers, `!`, asymptotic notation, a function of an unknown, an approximation step such as sin θ ≈ θ, an angle range); the reason is named |
| ST-UNDEC-002 | warning | deterministic | a numeric relation depends on a symbol with no stated value and no admissible booklet reading |
| ST-UNDEC-003 | warning | deterministic | NEW (STEM repair 2, section 22): a Given value could not be set against the request (no request value of its kind, no supplied table naming it, or a bare number the request does not state); one finding per statement naming each such Given; zero and a data-booklet constant at the booklet's value are neither checked nor named |
| ST-UNDEF-001 | warning | numeric | a written expression is undefined (division by an exact zero, an even root of a negative value, the logarithm of a non-positive value, 0⁰, tan at a pole, arcsin or arccos outside [−1, 1]); no check is built |
| ST-UNIT-001 | warning | deterministic | a unit expression is not recognised; the relation is checked as written only, at warning severity |
| ST-UNIT-002 | info | deterministic | an ambiguous unit symbol (M: molar or mega) is checked under both readings |
| ST-DIM-001 | warning | deterministic | the two sides of a stated relation have different dimensions (units read unambiguously) |
| ST-DIM-002 | warning | deterministic | a sum or difference of terms with different dimensions |
| ST-ALG-001 | warning | deterministic | a mathematics step takes only the non-negative square root, and no domain restriction is stated (the algebra is still checked under that side condition) |
| ST-CHEM-001 | warning | deterministic | a chemical equation cannot be read (unknown element symbol, isotope notation, a bound exceeded); its balance is not checked |
| ST-CODE-001 | info | deterministic | a code block is present; it was not executed and not checked |
| ST-SCOPE-001 | info | deterministic | a symbol is rebound to a different value inside the answer; substitutions match any binding |
| ST-LIM-001 | warning | numeric | an expression or literal exceeds a front-end or IR bound (span, links, nodes, depth, exponent, digits after factoring, symbols, intervals); not checked |
| ST-LIM-002 | warning | deterministic | more relations than the per-report check cap (128), or more math spans than the per-report reading cap (1,024); the count and the first unchecked ids or statements are named |
| ST-INTERNAL-001 | warning | deterministic | the STEM pack failed internally while building checks, an enclosure failed its cross-check against `math`, or a built problem was refused by `Problem.model_validate`; the affected checks are missing and must not be read as passed. When the failure leaves the report with no STEM check (the front end failed and returned an empty document, or the pack raised), the hub's PACK-INTERNAL-001 (error) stands beside it |
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
  bound symbols it uses. A claim that holds a planned computation (an engine check of its
  arithmetic, substitution, conversion, algebra, roots, balance, Boolean identity or based
  numeral) also offers the computing command words (calculate, determine, find, convert,
  solve, …): it does compute. An equation-only correct answer then does not get a heuristic
  INT-REQ-004 warning. The method stays `lexical_heuristic`.
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

Receipts are unchanged in shape:
- `formal_checks` holds `ConstraintResult(constraint_id=check_id, method="formal",
  formal_result_id, formal_status)`;
- `structural_findings` holds the ST findings;
- the summary keeps counts "N (ok, FAILED, undecided)", names at most 8 FAILED and 8
  undecided ids, shows the code histogram (ST-* included), and ends with `_SCOPE_TAIL`.

Check ids are short and stable, as in section 8.1.

### 11.5 `integrity/ledger.py`

Synthesis-fidelity figure extraction (INT-LEDGER-0xx) reads scientific notation (`3.0e8`,
`6.67 × 10⁻¹¹`, `1.2*10**6`) through `stem.numbers.scan_number`. Such a figure is one figure
whose spellings are its exact decimal value and its normalised mantissa-exponent form, so
`3.0e8`, `3.0 × 10⁸` and `300000000` are the same figure. Before this change `3.0e8` yielded no
figure and `6.67 × 10⁻¹¹` yielded 6.67 and 10. A figure beyond the scanner's bounds (an exponent
over 99) is not read, and neither are its parts. Figures with no exponent are read as before.

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

## 21. STEM repair 1: readings added after the independent test of the overseer's STEM completion

An independent test planted STEM faults on copies of the round-7 answers and found six problems.
Five are the STEM front end's; each is fixed where the reading went wrong, for its whole class,
with a clean control for every new reading (`tests/stem/test_stem_repair1.py`; the overseer's
side is `docs/OVERSEER_DESIGN.md` section 32). The original translator's English, History and
generic readings are untouched.

1. **Prefixed Greek units** (section 6.1). `kΩ`, `MΩ`, `mΩ`, `GΩ` and `μΩ` are one prefixed unit,
   so a correct conversion holds (`2400 Ω = 2.4 kΩ`, `0.50 mΩ = 0.00050 Ω`) and a wrong one fails
   (`2.4 Ω = 0.024 kΩ`); `12 V / 2.4 kΩ = 0.0050 A` is checked in SI. Before, the false alarm on the
   correct conversion was INT-SUBJ-001, and `MΩ` or `mΩ` left the line unchecked (ST-UNDEC-002).
   The independent test's "Given in kΩ where the task states the resistance in words" fault had
   been reported as a translator gap of task words; its cause was the same reading.
2. **English words are no units** (section 6.2): `as`, `am`, `at` after a number; and `counts` is a
   count, so `1600 counts min⁻¹ × (1/2)⁴ = 100 counts min⁻¹` is checked (the decay line had ended
   its span at "counts").
3. **Rule `bare-factor`** (section 6.5): ST-DIM-001 when one side has a single unit-bearing operand
   and bare numbers no stated value or constant explains.
4. **Combination and permutation counts** (`lexer.combination_at`): `⁵C₂`, `ⁿCᵣ`, `₅C₂`, `5C2`,
   `10C3`, `nCr`, `C(5, 2)`, `C(n, r)`, `C(n, k)` (r ≤ n for digits, so a point `C(2, 3)` is not one; the letters n, r
   and k only, so a function or a point `C(x, y)` is not one), `₅P₂`,
   `nPr`, and in LaTeX `^{5}C_{2}`, `{}^5C_2` are one construct, read as a binomial coefficient or
   a permutation count outside the encodings: the relation is ST-UNDEC-001 with that reason,
   never silently unchecked (before, `⁵C₂ = 10` was read `5 × C × 2` or not at all). Chemical
   formulas (`C2H4`, `H₂C₂O₄`) and a temperature `2.5C` are not read so.
5. **Rule `rounding-cue`** (R8): a value restated with a rounding the prose states in its clause
   ("To the nearest whole number, the decrease is 61%", "Correct to 2 significant figures, …")
   or right after it ("60%, to 2 s.f.") is a restated result of the chain before it, checked with
   the stated rounding's half-width; the figure of the phrase (the 2 of "to 2 s.f.") is never the
   restated value.
6. **Rule `inline-restatement`**: a value after ", so", "i.e." or "giving" right after the chain
   its line closes (`P = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W`) is a restated result; a consequence
   (`= 6.0 N, so 12 N in total`) is not (only punctuation, a bracket or a stated rounding may follow
   the value).
7. **Quantities the request names in words** (`spans`): a number after a multi-letter name word
   and before a unit ("a battery of emf 12 V") is a request quantity, so a Given that contradicts
   it (`Given: ε = 9.0 V`) is set against it on the Given (a `giv` check against the request's
   quantities of the same dimension).
8. **Rule `named-change`**: the value a change starts from ("The external resistance rises from
   2.4 Ω to 4.0 Ω") restates the value the answer stated earlier for the quantity the sentence
   names: the final value of a chain whose label words hold every word of the name (a label in
   brackets after the value, the statement's label before its chain, the chain's word label, or
   the part's question for the part's last value). A `res` check at warning severity (INT-SUBJ-004:
   the quantity is matched by its words), naming both statements; nothing when no earlier value,
   or more than one, carries the name with the same dimension. The relation never changes a
   claim's role (`adapters/stem_specialist/parser.py` leaves named relations out of roles).
9. **Rule `table-data`** (`datatables.py`; R9): the pipe tables of the supplied texts (a header row
   of column names with their units, the first column the key) are read with the one number
   scanner and the unit parser, all bounds fixed. A change between two rows ("between 25 °C and
   30 °C, an increase of 22 mm³ per g per hour") or a value at a row ("from 18 … at 10 °C to 92 …
   at 35 °C") is a `giv` check against the cells taken as written, at warning severity (which rows
   and which column the prose means is a reading); the column is the table's only column of
   numbers or the one the clause names; nothing when a row, the column or the unit is not read
   unambiguously. The statements are the same with and without the supplied data.
10. **Rule `related-statements`** (`relations._related_statements`, `FormalCheck.related_claim_ids`,
    the channel's failure finding): a substitution names, besides its own statement, for each
    symbol it substitutes, the one statement that states a value of it before the substitution,
    latest first. When it fails, its INT-SUBJ-001 names those claims after its own, so a wrong
    formula applied consistently (`V = ε + Ir`, `V = 12 V + (4.14 A × 0.50 Ω) = 14.1 V`) is named
    where its value is stated as well as a line later (`P = (9.93 V)² / 6.0 Ω`). A symbol whose
    value several statements state, or that the relation's own statements state (a Computer
    Science trace step's clause), names no statement: none is named on a guess. The formal check
    itself still names its own statement only.
11. **The tolerance rule's statements** (section 5.2): the short form and the pack's D31 now say
    what the checks apply (R1's trailing zeros, R2's precedence of `≈`, the half-width of a stated
    value set against another); `tests/overseer/test_stem_completion.py` executes each statement
    against `tolerance.half_width`, `tau_for` and whole checks decided by the engine.

On the recorded round-7 answers the new readings add only checks that hold: bi-t13 four `giv`
checks of its table values, ess-t13 two, ph-t13 five `res` checks (its four named changes and
the inline restatement "16.4 W, so 16 W"), ph-p7b the decay line (`stem-eq-9`). Remaining translator gaps,
each measured on a planted copy and reported, not counted: a factorised line or a roots line after
a comment line is read as a new equation (equations-factorising, maths-roots; joining across a
comment risks false errors on genuine answers), and derivatives and integer powers beyond 12 stay
outside the encodings (formulas-derivative, maths-finance-value: ST-UNDEC-001, as on the recorded
answers).

## 22. STEM repair 2: readings added after the second independent test

A second independent test planted STEM faults on copies of the round-7 answers and found eight
problems: a false error on correct integer working, contradictory Givens and table values with
neither a check nor an ST code, the wrong value taken from a quote in the relay, a slip passed in
Form S, statements skipped silently, and a pack that read that silence as checked. Each is fixed
where the reading went wrong, for its whole class, with a clean control for every new reading
(`tests/stem/test_stem_repair2.py`; the overseer's side is `docs/OVERSEER_DESIGN.md` section 33).
The original translator's English, History and generic readings are untouched.

1. **Integer arithmetic** (`lexer`, `parser`, `nodes.IntOp`, `to_ir`). The words `mod`, `modulo`
   and `div` (any case) between two operands, `//`, LaTeX `\bmod` and `\mod`, and in Computer
   Science `%` are integer operators at the precedence of × and ÷. The reader had dropped the left
   operand and the word, so `17 mod 5 = 2` was checked as `5 = 2` and failed (an INT-SUBJ-001 on
   correct work; `17 div 5 = 3`, `9 div 2 = 4` and `9 mod 2 = 1` the same). The encoder writes
   `to_real(mod(17, 5))` and `to_real(idiv(17, 5))` with the IR's integer operators: the left
   operand a non-negative whole-number expression (`+ − ×`, powers up to 12, nested integer
   operations), the divisor a positive whole number as written; any other operand is
   ST-UNDEC-001 with its reason (a negative remainder: languages round it differently). A
   quotient stated with its remainder (`17 ÷ 5 = 3 remainder 2`, `rem 2`) is two checks, the
   integer quotient and the remainder; a congruence (`17 ≡ 2 (mod 5)`, `17 ≡ 2 mod 5`) is
   `17 mod 5 = 2 mod 5`, the bracket no factor. A word that is not between two operands ("the
   mod operator", `divmod`) is a word.
2. **Verbal arithmetic is read once.** A math run wholly inside a verbal span ("3 times 4 = 12")
   is not read again, so its tail `4 = 12` is no second, false check.
3. **Rule `fragment`.** A relation whose left side is a single value that continues the words
   before it ("the remainder when 17 is divided by 5 = 2", "20% of 50 = 10", "12 over 4 = 3",
   "twice 4 = 8") is written partly in words: ST-PARSE-001 naming the word, never the check
   "5 = 2" (before: a false INT-SUBJ-001). A whole expression after a word ("The value of
   3 × 4 = 12") is checked as before.
4. **Rule `unread-relation`** (`document._unread_relation_signs`). A statement with a relation
   sign (`= ≈ ≠ ≤ ≥ ≡ < >`) between maths (a digit, a bracket, a one-letter symbol) that no span
   reads is ST-PARSE-001: `17 % 5 = 2` outside Computer Science. A sign between words, a doubled
   sign or an ASCII arrow (`==`, `->`, `=>`) and a bond glued between letters (`O=O`) name no
   relation of values; a chemistry atom tally (`C 3 = 3`) and an article label (`the Al = …`) are
   read as before. An amount written after a currency sign is no maths the reader holds: a sign
   beside one names nothing (a reading that named it raised ST-PARSE-001 on the corpus's correct
   `$7052.99 − $5000 = $2052.99`, and was not kept).
5. **Rule `question`.** A relation the answer asks and answers is checked as answered: "Is
   38 = 67? No." checks 38 ≠ 67, "Yes" the relation; with no answer it claims nothing. The
   check's statement names the relation decided ("(the relation decided: 67 ≠ 67) (rule
   question)").
6. **Rule `given-kinds`** (`relations._givens`). Every Given value (a symbol given a number in a
   statement that begins "Given", "Data", "Known" or "We know", or in the list a line "Given:"
   opens) of an answer to a request is set against the request's value of the same symbol, else
   its values of the Given's kind: for a Given with a unit, the request's quantities of the same
   dimension (as before); written with `%`, "per cent" or "percent", the request's percentages;
   written with a word after it, the request's numbers written with the same word ("5000 euros"
   against "4000 euros", "6 years" against "5 years"); a bare number, the request's number it
   equals. A Given naming a row and a column of a supplied table is set against that cell (rule
   `table-data`). Each is a `giv` check at warning severity whose statement names what it is
   compared with ("compared: …"); a percentage is compared in SI with its half-width scaled too
   (3.9% had passed against 3.6%), and two whole numbers with no unit exactly. A Given none of
   these reads is ST-UNDEC-003, one finding per statement naming each such Given and why; a
   bare number is never failed, since it may be a conversion (0.036 for 3.6%, 12 for "monthly").
   Zero (a condition the request states in words: "from rest") and a data-booklet constant at
   the booklet's value are neither checked nor named, and with no request (a relay) no Given is
   set against anything. A Given that may be a numeral written with a thousands space ("4 000")
   is ST-PARSE-001, never read as 4; one written after a currency sign (`P = €4000`) is not read
   (item 4).
7. **Rule `named-given`.** A value the prose states for a quantity the request names by its
   words ("The battery's emf is 9.0 V" for "a battery of emf 12 V") is set against that
   quantity (warning: the quantity is matched by its words).
8. **Rule `table-operands`.** The numerals of a line's computed side that are cells of the
   column the line or its part's question names are set against the cells of the rows the line
   names ("From A to C …"), or else the rows its part's question names (warning), when the line
   takes as many different cells of that column as rows are named: `(9.6 − 6.1) ÷ 9.6 × 100` for
   the decrease from A to C (6.1 is site B's) fails; a mean of three rows in a part whose
   question names two is another computation and is not read.
9. **Rule `restated-binding`.** A value given to a symbol or a function value after "so" (or
   "i.e.", "hence", "thus", "giving") right after a chain on the same line is set against the
   chain's final value, its central value when it states an uncertainty: the relay's
   `“t = 8 h: 820 − 20 = 800 ± 16 counts min⁻¹” (so C(8) = 820)` fails against 800 (warning).
   Not when the symbol is one the chain solves for or computes.
10. **Rule `exact-carry`.** A value the written arithmetic gives exactly, from numerals none of
    which carries a rounded result, has no rounding interval: a later line that carries it is
    decided in Form E, and a restatement set against it has no half-width of its own. A sum of
    count rates written with units (`100 counts min⁻¹ + 20 counts min⁻¹ = 130 counts min⁻¹`) had
    passed in Form S over the intervals of carried values.
11. **Asides, premise cues and prose sums.** A math run whose only relation sits inside a bracket
    after its first word starts inside the bracket ("greatest at C (2.0 km = 200 m)" is a
    conversion check); after a relation introduced by "From", "Since", "Because", "As", "Using",
    "Rearranging" or "By", the relation that follows it on the line after a comma, over the same
    symbols, is an algebra step from it (rule `premise-cue`: "From c = n/V, n = c/V …" fails, "n =
    cV" holds); a sum in a sentence of prose ("A measured rate would be 100 + 20 = 130 counts
    min⁻¹") is checked.

On the recorded round-7 answers the new readings add only checks that hold: bi-t13 and ess-t13
two `giv` checks each of their part (a) operands (rule `table-operands`), ph-p7b seven of its
corrected rates, maa-p7b two `res` checks of the values it takes after quoting them (rule
`restated-binding`); no ST-UNDEC-003 or new ST-PARSE-001 is raised on any of them. The arena's
maa-p7b arithmetic mutation (`1620 − 20 = 4600`) is now also named by the restatement
`(so C0 = 1600)` that no longer matches it, on the same claim. Remaining limits, stated: a
Given derived from the request's values and listed among them (a monthly rate 0.3% beside the
annual 3.6%, a resistance computed and listed as given) fails its check as a warning, as a
derived Given with a unit already did; a bare number that contradicts the request is named
unchecked, not failed; an amount written after a currency sign (a Given `P = €5000`, a relation
`$7052.99 − $5000 = $2052.99`) is neither read nor named, as before this repair.

## 23. STEM repair 3: readings added after the third independent test

A third independent test planted STEM faults on copies of the round-7 answers and found seven
problems: a false error on correct work (a value stated under a condition read as a unit
conversion, and such a Given left with neither its check nor its ST code), an arithmetic slip
passed inside a stated uncertainty, the measured cell substituted for the value the answer
corrected it into, Givens contradicting a supplied text's prose named exactly as the correct
ones, values restated in the wrong unit where the task or its table gives the unit, wrong
formulas and stated precision unnamed, and pack text that disagreed with the code. Each is fixed
where the reading went wrong, for its whole class, with a clean control for every new reading
(`tests/stem/test_stem_repair3.py`; the overseer's side is `docs/OVERSEER_DESIGN.md` section 34).
The original translator's English, History and generic readings are untouched. No ST code was
added.

1. **Rule `value-at`** (`relations._value_at`, `_value_at_chain`, `_value_at_cells`,
   `_value_at_tables`; `document._build` gives a Given's condition item the source
   `condition`). A maths run right after a condition word ("at", "when") that opens with the
   condition and then states the named quantity's value ("oxygen uptake at 30 °C = 80 mm³ per g
   per hour", "the count rate at t = 8 h = 820 counts min⁻¹", "time at 30.0 °C = 33.1 s") states
   the quantity's value under the condition: a `label` binding that carries the condition, never
   a relation between the condition and the value. It had been read as the conversion
   `30 °C = 80 mm³` and failed (INT-SUBJ-001 with ST-DIM-001 on correct work). It is read only
   when the condition and the value are of different kinds, so `at 25 °C = 298 K` stays a
   conversion. The condition binds nothing (its symbol keeps its other values). A Given so stated
   (and `Given: at t = 8 h, C = 820 counts min⁻¹`) is set against the supplied table's cell at the
   row its condition names, in the column its name names; when its name fits no single column
   ("time" beside three timed trials), against that row's cells of every column of its
   dimension, one of which it must match; with no supplied table to read the row of, it is
   ST-UNDEC-003. A value so stated outside a Given ("The uptake at 20 °C = 40 mm³ per g per hour,
   and at 30 °C = 80 …", the second clause taking the first's name) is set against the table when
   the row and the column are read unambiguously, and nothing is planned otherwise.
2. **Rule `central-value`** (`checks._eq`). A stated value written with its absolute
   uncertainty, `S ± u` ("586 − 20 = 566 ± 12"), is checked at its central value under the
   tolerance rule; u never widens h. The band had been added to h, so a slip within it
   (`586 − 20 = 556 ± 12`) was ENTAILED. The check's statement says so ("the computed value is
   set against its central value … the uncertainty itself is not checked (rule
   central-value)"). A Given written with its uncertainty ("Given: T = 20.0 ± 0.5 °C") had no
   value node, so neither a check nor an ST code; its central value is now the Given value.
3. **Rule `processed-data`** (`relations._processed_data`). A line that processes one cell of a
   supplied table into another value of its quantity ("t = 0 h: 1620 − 20 = 1600 ± 32 counts
   min⁻¹") states the processed value of that row. A line of a later part whose question, or the
   line itself, names the processed quantity by the word that sets it apart from the column
   ("corrected": the words of the processing part's question and of a word formula stated in it
   that the column's name, the key column's name and the command words do not hold), and that
   takes the raw cell instead ("C = 1620 counts min⁻¹ × (1/2)⁴"), is a `giv` check of the raw
   cell against the processed value at warning severity (which of the two the line means is a
   reading), naming both statements. Not read: a line of the processing part itself, a part that
   names no such word, a cell two rows hold, a line that processes the raw cell again into the
   processed value ("C₀ = 1620 − 20 = 1600 counts min⁻¹"), and a line whose result is no value of
   the column's quantity (a percentage or a ratio of the raw cell: "20/1620 × 100 = 1.2% of the
   first reading"). The last two were found closing the class: in the part that asks for the
   corrected rate they had been set against 1600 and failed.
4. **Rules `supplied-values`, `given-digits` and `given-uncertainty`** (`document._supplied_reading`,
   `relations._given_candidates`, `_uncertainty_candidates`, `checks._giv`). The values a text
   supplied with the request states in its prose (outside its tables: quantities with a unit the
   table of units reads, after ASCII exponents and "+/-" are read, and percentages) are
   candidates for a Given whose name shares a word with the sentence that states them ("Given:
   volume of thiosulfate = 40.0 cm³" against "50.0 cm3 of … sodium thiosulfate solution"; "C0 =
   1600 counts min⁻¹" names nothing the text writes and stays ST-UNDEC-003). They had not been
   read, so a contradicting Given got the same ST-UNDEC-003 as the correct one. A Given restates
   its data as written: every written digit of a whole number counts, its trailing zeros too, on
   both sides (rule `given-digits`; 30 had held against 20, h = 5 each). A value written as an
   uncertainty ("+/-0.5 °C", "+/-2%", in a supplied text or the request) is no value of a
   quantity; it is one of the uncertainties stated, with the unit written after it. A Given named
   as an uncertainty (its name holds "uncertainty", "precision", "resolution" or "tolerance") or
   written as one ("Δθ = ±0.5 °C") is set against those uncertainties, of its dimension or as
   percentages (rule `given-uncertainty`), never against a value of its quantity; with none of
   its kind stated it is ST-UNDEC-003. Found closing the class: "Given: thermometer uncertainty =
   0.5 °C" had failed against the request's 20 °C and 60 °C (a false warning on a correct Given),
   and a Given written "±0.5 °C" had neither its check nor its ST code.
5. **Units given only in the task or its table** (`datatables.ascii_exponents`, `DataColumn.unit_ascii`,
   `spans`, `parser._unit_after`, rule `restated-unit` in `relations._restated_units`). A header
   unit written with ASCII exponents ("mm3 per g per hour", "mg dm-3") is read as written with
   superscripts; a unit written "per" another ("mm³ per g per hour") is read whole after a number.
   A value the prose gives from a supplied table is compared in SI when it and the header carry
   units of one dimension, so a value restated in another unit fails ("from 18 cm³ per g per hour
   at 10 °C" for the table's 18 mm3 per g per hour); a correct conversion (0.018 cm³) holds. A
   value the answer states (in prose, or for a symbol or a named quantity outside a Given) with the
   number of a quantity the request or a supplied text states and a unit of the same dimension but
   another size ("the background of 20 counts s⁻¹" where the task states 20 counts per minute) is
   a `giv` check against that quantity in SI, at warning severity, which fails (rule
   `restated-unit`); the task's own unit, another number, and temperatures (a change of 20 K is a
   change of 20 °C) plan nothing.
6. **Wrong formulas and stated precision** (rules `percentage-change` and `half-lives`, the stated
   rounding of a stated value). A line that computes a percentage increase or decrease as a
   difference of two values over one of them, times 100, is set against the definition, the
   change over the starting value (the larger for a decrease, the smaller for an increase, the
   direction read from the word beside "percentage" in its statement or its part's question):
   "(9.6 − 3.8) ÷ 3.8 × 100 = 152.6% decrease" keeps its arithmetic right and fails (warning); a
   line that divides by the starting value is the definition and plans nothing more. A number of
   half-lives the prose states ("32 h is 4 half-lives", "four" read as 4) is set against what the
   answer computes with it: n × T½ (the latest half-life the answer states) against the time, and
   the exponent of a power of ½ (or 0.5) written after it in the statement against n (both
   warning); "× (1/2)³ = 200" and "32 h is 5 half-lives" fail. A stated value restated on its line
   with a stated rounding ("R = 2.4 Ω (the external resistance), or 3 Ω to one significant figure")
   is checked as a restatement under that rounding (a bracketed label between the value and the
   restatement is read through), and fails (INT-SUBJ-001); "2 Ω" holds.
7. **A percentage is never a restatement of a quantity of a dimension.** "… = 820 counts min⁻¹" and a
   later "2%" had been paired as a result and its restatement (a false INT-SUBJ-001 in the tester's
   ph-p7b control).

On the recorded round-7 answers the new readings add only checks that hold: ph-p7b two (the
time "32 h is 4 half-lives" as four times its T½ = 8.0 h, and the power (1/2)⁴ after it), on
every one of its eight records; no other recorded STEM answer gains or loses a check, and no
ST-UNDEC-003, ST-PARSE-001 or ST-DIM-001 is raised on any of them. Remaining limits, stated: the
value a change ends at that the prose computes itself ("the current falls from 4.1 A to 2.6 A",
"from 9.9 V to 11.7 V") is not checked (its start is, against the value stated for the quantity);
a sum with a symbolic bound or of more than 24 terms, a product ∏, an ellipsis written in LaTeX
and a symbolic power stay ST-UNDEC-001; two whole-number Givens a unit apart hold under the rule
for a value set against a value (h of each side), as before.

## 24. STEM repair 4: readings added after the fourth independent test

A fourth independent test planted STEM faults on copies of the round-7 answers and found eight
problems: two false errors on correct work (a Boolean expression evaluated under the values its
statement gives read as an identity over every assignment; a substitution in a later part that
takes the value the prose says a quantity changes to, set against the symbol's earlier values only),
a Given uncertainty written with "±" and "%" with neither its check nor its ST code, a result
restated after ", so" with a word after its number never read, values at the lettered rows of a
supplied table never set against it, a 12% slip passed through a rounding interval on exact
working, a wrong stated uncertainty and arithmetic slips under 1/100 passed within the documented
limits, and the contained run's adjudication gate counting an entry raised in the wrong pass (the
last is the overseer's, `docs/OVERSEER_DESIGN.md` section 35). Each reading is fixed where it went
wrong, for its whole class, with a clean control for every new reading (`tests/stem/test_stem_repair4.py`).
The original translator's English, History and generic readings are untouched. No ST code was
added.

1. **Rule `boolean-values`** (`relations._boolean`, `_boolean_values`; `checks._bool`). A value a
   statement gives a Boolean input ("A = 1") is recorded, and a Boolean relation whose statement
   gives its inputs values ("With A = 1 and B = 0, NOT A OR B = 0.", "If A = 1, then NOT A = 0.",
   "NOT A OR B = 0 when A = 1 and B = 0.") is decided under them: each input takes the latest value
   before the relation in its statement, else the first after it, and an input given none stays
   free ("With A = 1, A OR B = 1" must hold for each B). When its own statement gives none, the
   nearest earlier statement of its paragraph that gives one does, when it sets values up: it ends
   with a colon, opens with a setup word ("Let", "Take", "Suppose", "Assume", "Given", "With",
   "When", "If", "For", after "Now" or "Here" too), or states nothing but the values ("A = 1, B =
   0.", "Test case: A = 1, B = 0."); or it is the statement right before and the relation's opens
   with "Then", "So", "Hence", "Thus" or "Therefore". A setup ending with a colon sets up the
   paragraphs after it too, across Boolean display lines only. A statement that says more than the
   values ("A = 0 is the reset state.") sets nothing up: the relation after it stays an identity, so
   a wrong identity still fails. A name defined by an expression ("X = A AND B") and later given a
   value under stated inputs ("With A = 1 and B = 1, X = 1") is its definition evaluated there. The
   check carries the values as premises (`VAL_*`), titles itself "the Boolean evaluation" and names
   the values; it expects UNSATISFIABLE over the negation, as an identity does. Before, every such
   relation was an identity, so correct evaluations failed (INT-SUBJ-001).
2. **Rule `changed-value`** (`relations._changed_values`, `scope.Scope.changes`,
   `checks._changes_before`; `_NAME_LEADS` gains the subordinating words). The value the prose
   gives a quantity at the end of a change it states ("the current from the cell falls, from 4.1 A
   to 2.7 A", "falls to", "becomes", "is now") is recorded for the symbol the quantity's words name
   (rule named-change's reading: one symbol, the same dimension). A substitution stated after the
   change, in its statement ("V = 12 V − 2.7 A × 0.50 Ω = 10.65 V, because the current … falls, from
   4.1 A to 2.7 A") or anywhere in its part may take that value, as it takes a binding, and its
   check says so; one in an earlier part never does, so part (c) taking part (e)'s current still
   fails. The value itself is not checked, never becomes a binding (no rebinding note, no carried
   value), and nothing is recorded when the words fit no symbol or several.
3. **Rule `given-uncertainty` for "±", "+/-" and "%"** (`normalize.reading_view`,
   `relations._givens`, `_stated_value`, `_value_with_uncertainty`). "+/-" written before a number
   reads as "±" (elsewhere, "+/- buttons", it stays as written). A Given written as an uncertainty
   in per cent ("Given: count rate uncertainty = ±3%") is set against the uncertainties the request
   and its supplied texts state ("+/-2%"), as one with a unit was; the uncertainty written with a
   Given value ("T = 20.0 ± 0.5 °C", "1620 counts min⁻¹ ± 2%") is too, when an uncertainty of its
   kind is stated (otherwise it is not read; the central value is always checked). A Given written
   with its uncertainty after the part's formula of its symbol ("Given: ε = 12 ± 0.1 V" after "ε =
   I(R + r)") is a Given, never the formula evaluated at it (it had neither its stem_given check
   nor an ST code). A Given in a maths span the branch cannot read whole ("1620 ± 2% counts min⁻¹",
   a unit after a per cent sign) is never read in part: its ST-PARSE-001 names the statement (its
   condition "t = 0 h" had been read as a Given and failed against the request's t = 32 h).
4. **Rule `rounding-cue` with a unit word** (`relations._results`, `_unit_words`, `_rounding_cue`,
   `_clause_ends`; `document._read` reads a number on a line of working when it is restated after
   the chain it closes). A result restated after ", so" may have a word naming its unit after its
   number ("= 4773.74, so 4775 euros to the nearest euro", "so 4775 euros.") or none ("so 5903 to
   the nearest euro"), and a rounding may name the whole unit ("to the nearest euro", "to the
   nearest ampere" for a value in A), a place with the unit after it ("to the nearest ten
   euros"), or a part of the unit (`_SUBUNITS`: "to the nearest cent" for a value in euros or
   dollars, "to the nearest penny" for one in pounds) or another unit of a value's dimension ("to
   the nearest milliampere" for a value in A): the half-width is half that unit, place or part. A
   word is read as the unit only when it is the word the task writes after its numbers ("4000
   euros") or the value's unit spelled out; "so 2 years of interest are missing" is a
   consequence, not a restatement, and "to the nearest dollar" for a value in euros reads nothing
   (found closing it: "to the nearest cent" had read nothing too, so a value one cent off held
   with only its arithmetic checked).
5. **Rule `row-value`** (`relations._row_values`, `_row_check`, `_count_head_words`). A value a
   statement or the prose gives at a row of a supplied table, named by a site's letter ("Dissolved
   oxygen at site C = 3.8 g dm⁻³.", "At site C, dissolved oxygen is …", "nitrate at E (4.1 mg
   dm⁻³)", "… at C (2.0 km), where it reaches 3.8 mg dm⁻³", "site A has the least nitrate (…)") or
   by a number with the key column's unit ("the measured count rate at 8 h is 830 counts min⁻¹"),
   in the column its words name (every word of the column's name, or the quantity a column counts:
   the words before "per", "mayfly nymphs"), is a `giv` check against that cell, in SI, at warning
   severity. Nothing is planned unless the row and one column are read; a value whose unit, or the
   unit written right after it, has another dimension than the column's ("at C (2.0 km)") is not its
   value; "Let C = 3.8 mg dm⁻³" is a symbol, not a site.
6. **Rule `exact-carry` for exact working** (`checks._exact_result`, `_exact_mode_chain`). A
   numeral that carries an earlier result of exact working ("T = ln 2 ÷ ((ln 2)/8) = 8": written
   "=", no approximate cue, every numeral exact) is exact, with no rounding interval; it had ranged
   over [7.5, 8.5], which with τ = 1/20 passed "8 ln 2 ÷ ln(1568/816) ≈ 9.5 h" (8.49). A rounded
   result ("T = 0.693 ÷ 0.0866 = 8.0") keeps its interval.
7. **Rules `stated-uncertainty` and `operand-precision`** (`relations._stated_uncertainties`;
   `checks._operand_rounding_tau`, `_rounding_bound`, `_trailing_zero_whole`). When the answer
   states how it obtains its uncertainties as a percentage of a value it names ("each corrected
   value has an absolute uncertainty of 2% of the measured value"), an uncertainty a later line of
   its part writes with its value (`S ± u`) and that takes exactly one cell of a supplied table's
   column whose name holds that word is set against that percentage of the cell ("1131 ± 33": 2% of
   1151 is 23.02), only u's own half-width banding it, at warning severity. For "=" in written
   arithmetic, when every operand of the computed side is a written numeral (no carried result,
   constant, symbol or function value; + − × ÷, integer powers, signs and per cents), τ is twice the
   largest relative change the rounding of those numerals can make to the computed value, exact
   interval arithmetic rounded up to a millionth, when that is below 1/100: "4000 × 1.036³ =
   4467.74" fails (τ = 0.29%) and so does "586 − 20 = 564 ± 12" (whole numbers are exact: τ = 0).
   A stated value that is a whole number ending in zero, written without a point, keeps 1/100.

On the recorded round-7 answers the new readings add only checks that hold: ess-t13 six (its
values at sites A to E, rule `row-value`), ph-p7b seven (its corrected rates' uncertainties, each 2%
of the measured value, rule `stated-uncertainty`), on every one of their records; maa-p7b's check
of the quoted "0.693/8.0 h = 0.087 h⁻¹" is decided in Form E instead of Form S (its 8.0 carries the
exact T = 8 of its part (b): rule `exact-carry`), and holds as before; no other recorded STEM
answer gains or loses a check, and no ST-UNDEC-003, ST-PARSE-001 or ST-DIM-001 is raised on any of
them. Remaining limits, stated: an exact-mode line whose operands and result are whole numbers
("1000 ÷ 3 = 330") is decided exactly, as before; a list item written "- NOT A = 0" is
ST-PARSE-001 (the dash is read as a minus); a value at a row whose phrase names no single column
("The time at 30.0 °C is 36.1 s" beside three timed trials) is not read; a rounding to a part of
a unit outside `_SUBUNITS` ("to the nearest kopeck") reads nothing.

## 25. STEM repair 5: readings added after the fifth independent test

A fifth independent test planted STEM faults on copies of the round-7 answers and found four
problems: four false errors on correct physics and computer-science working (the line that
evaluates a formula after its correct rearrangement read as an algebra step from the
rearrangement, its other symbols pinned to values of other parts; a symbol reused in a part for
another quantity set against the other part's value; a count of passes after "so" set against a
chain three statements before), a relation the branch read but neither checked nor named (a
prose line giving a quantity's value as a relation in stated symbols, "The battery's power output
is 12 V × I = 60 W.", with the pack saying the branch names what it reads and cannot check), a
conversion and a restated rounding written in prose missed, and a false warning on correct
uncertainty working (2% of the raw cell set against its processed value). Each reading is fixed
where it went wrong, for its whole class, with a clean control for every new reading
(`tests/stem/test_stem_repair5.py`); the overseer's side is `docs/OVERSEER_DESIGN.md` section 36.
The original translator's English, History and generic readings are untouched. No ST code was
added.

1. **Rule `rearranged-formula`** (`relations._sequence`, `_rearranges_formula_of`). When the
   relation before a line is an equation in exactly the symbols of a formula the answer states for
   a symbol, with that symbol (a rearrangement: "From P = V²/R, R = V²/P.", "Rearranging, R =
   V²/P.", "V² = P × R", "V²/P = R", "I × r = ε − V", "R + r = ε/I"), and the line gives the
   formula's symbol a value or writes its formula with values put in ("P = (9.93 V)² / 6.0 Ω"), the
   line evaluates the formula, as it does right after the formula itself: its substitution is
   checked against the formula, never an algebra step from the rearrangement. The rearrangement is
   still checked as a step from the formula (a wrong one, "R = P/V²", fails), and so is every other
   line that solves an equation ("2x + 3 = 7", then "x = 2"). Before, the evaluation was a step
   with R and V pinned to part (a)'s 2.4 Ω and part (c)'s 9.9 V, so correct working failed.
2. **Rule `part-value`** (`relations._substitution`, `_part_values`, `_part_results`;
   `checks._sub_pairs`, `_part_value_expr`). A substituted symbol whose every binding stands in
   another part, and whose value here matches none of them, may stand in this part for another
   quantity: its value also matches when the line's numeric side gives a value the part already
   gives, before the line, to the quantity the chain computes (its lone head's value, "As a check,
   P = I²R = (1.655 A)² × 6.0 Ω = 16.4 W." after "P = … = 16.4 W"; with no lone head, or none with
   such a value, a result of the part of the numeric side's dimension, "As a check, I²R = …"), and
   when it matches a result the part computes before the line with the symbol's dimension ("The
   current in it is 9.93 V ÷ 6.0 Ω = 1.655 A."). The engine decides each match (`|N − H| ≤ h(H) +
   τ·|N|` for the part's result, the binding band for a part's value). A value the part's prose
   states for a quantity named only by the stated quantity's words is no such result: it may
   restate the other part's quantity ("the terminal potential difference, 9.93 V" against part
   (c)'s V), which the substitution must still be set against (STEM repair 1's related-statements
   test). A value stated nowhere is set against the bindings alone, as before (the third pass, item
   9, adds the prose that names another quantity, another part's value of the head and a
   computation in the symbol's place).
3. **Rules `inline-restatement` and `adjacent-restatement`** (`relations._results`). A value
   after its own statement's computing chain that is no inline restatement of it restates nothing
   ("Also log₂ 1000 ≈ 9.97, so 10 passes."), and a bare number (no unit, no per cent sign) restates
   only a chain of its own statement or of the statement right before it ("With n = 1000 items, so
   10 passes are needed." and "Also 2^10 = 1024 ≥ 1000, so 10 passes suffice." had been set against
   "1,000 ÷ 2^10 = 0.98" three statements before, naming its genuine claim). A value or a formula
   its own statement gives a symbol ("at $x = 1$ is 5", "the curve y = 3x² + 1 … is therefore 10")
   still names a condition or an object, never the chain it restates; a value with a unit or a per
   cent sign still reaches the last chain of its part, its dimension guarding the pairing.
4. **Rule `bound-relation`** (`relations._sub_or_equation`, `_prose_head`, `_bound_relations`,
   `_solved_in_prose`, `_equation_of_part_result`; `checks._sub_evaluate`). A maths run the prose
   gives as the value of a quantity it names, after "is", "are", "was", "were" or "equals" (also
   "is then", "is therefore"), is read as a chain headed by that quantity: its symbolic side under
   the stated bindings against its numeric side, a `sub` check ("The battery's power output is 12 V
   × I = 60 W."); a symbol with no stated value is named ST-UNDEC-002 ("The energy is 0.5 × k ×
   0.04 = 1.0 J."), as it is with a symbol head. Not when its part goes on to solve it for one of
   its symbols, in a statement ("…, so I = 1.65 A") or in its prose with a value of that symbol's
   dimension that matches none of its stated values ("…, giving a current of 1.65 A"), or in its
   own statement for a symbol with no value ("…, so the spring constant is 50 N m⁻¹"); not when one
   of its symbols has its stated values only in other parts and its numeric side is a result its
   part already states ("The power in it is I² × 6.0 Ω = 16.4 W." after "P = … = 16.4 W": an
   equation for the current in the 6.0 Ω resistor); not for a function written as applied ("the
   cost of 12 items is C(12) = …"), an equation the prose calls an equation, an expression or a law,
   or a run with no quantity named before it ("So 12 V × I = 60 W."). Found closing it: "E = 0.5 × k
   × 0.04 = 1.0 J" had been cut at a magnification suffix "0.5×" (`spans._RunFinder`): a "×" with a
   space before it and a symbol after it is a product.
5. **Rule `prose-conversion`** (`relations._prose_conversions`). A value the prose states and
   restates right after it in another unit of the same dimension, after "that is", "i.e.", "which
   is" or ", or", in brackets (alone, or after "or", "i.e." or "that is"), or after "is", "equals",
   "is equal to", "is equivalent to" or "is the same as" when the restated value ends its clause,
   "about" (τ = 1/20) allowed before it, is a unit conversion, a `cnv` check titled "the unit
   conversion the prose states". Two values in one unit, two dimensions, a unit the table does not
   read, anything else between them, a restated value its clause goes on after ("2.0 km is 500 m
   more than 1.5 km") and a first value that ends a range, a list or a comparison are not read.
6. **Rules `rounding-cue` for a value stated for a symbol, and `same-place`**
   (`relations._rounded_bindings`, `_rounding_cue`, `_last_sentence_end`, `_ROUND_BRACKET_RE`;
   `checks._compare`). A value stated for a symbol with a rounding its statement states ("To 3 s.f.,
   P = 16.5 W.", "P = 16 W to 2 s.f.", "P = 16.5 W (3 s.f.)") restates the symbol's last computed
   value in its part; a precision in brackets after a value is a stated rounding, and the full stop
   of "s.f.", "d.p.", "i.e." or "e.g." ends no sentence ("To 3 s.f. the power is 16.5 W." had lost
   its rounding). A restatement whose stated rounding is to the place the value it restates is
   written to must equal it: h is 0 (rule `same-place`), never the two half-widths added, which let
   "To 3 s.f., the power is 16.5 W." hold after 16.4 W. With no rounding stated, h(S) + h(S′) bands
   it as before.
7. **Rule `processed-data`** (`relations._processed_data`, `_percentage_of`, `_ratio_of`,
   `_stated_percentages`, `_quantity_values`) **and the per cent reading** (`checks._reading_modes`,
   `_percent_factor`; `to_ir.Reading.percent`). A line that takes a percentage of the raw cell
   (written with "%", "±2% × 1620" too, as the decimal of a percentage the answer, the request or
   its supplied texts state, or as a division by N with 100/N such a percentage, "1620/50"), or a
   ratio of it to another value of its quantity or a value set over it ("1620/820", "32.4/1620 =
   0.020"), takes the measured value on purpose and is not set against the processed value. A per
   cent taken of a number beside a unit whose SI factor is not 1 ("1620 × 2% = 32.4 counts min⁻¹",
   "±2% × 1620 = ±32.4 counts min⁻¹") is also read with the per cent as its fraction and the units
   as written ("as written, per cent as a fraction"): as written had read 2% as 2, and SI converted
   one side's unit only.
8. **The classes closed whole, a second pass.** Measured again on the repaired front end, each
   class had further phrasings of the same causes, each fixed at the same cause with its clean
   control: a rearrangement stated after "Making R the subject", "Solving for R" or "Transposing"
   is a step from the relation before it (`_STEP_WORDS`), so a wrong one fails ("Solving for R, R
   = P/V²." had been read as no step once the evaluation after it was no longer one); a relation
   the prose gives as a quantity's value after "equal", "is equal to" or "is given by" is read by
   rule `bound-relation` too (`_PROSE_HEAD_VERB_RE`); a conversion the prose states after "which
   equals", "which is equal to", "equal to", "equivalent to" or "or equivalently", after a
   semicolon, a colon or a dash before "that is" or "i.e.", after "converts to" or "is converted
   to", or after a comma and "about" (the restated value ending its clause) is read by rule
   `prose-conversion` (`_PROSE_RESTATE_RE`); and rule `processed-data` leaves unread a line that
   processes the raw cell inside its own arithmetic ("C = (1620 − 20) × (1/2)⁴ = 100 counts
   min⁻¹": a sub-expression holding the cell is exactly the processed value, `_processed_inline`),
   a share of the cell in any arithmetic form ("1620 × 2 ÷ 100", "1620 ÷ 100 × 2") and the bounds
   of the measured value ("1620 + 32.4", "1620 × 1.02", "1620 + 0.02 × 1620"), each read from the
   line as a·x + b in the cell x by exact rational evaluation of the written numerals
   (`_cell_linear`, `_share_or_bound_of`: a = p/100 or 1 ± p/100 with b = 0, or a = 1 and |b|
   within half a unit of its last digit of p% of the cell, p a percentage the answer, the request
   or its supplied texts state). Each had been a false INT-SUBJ-004 on correct working, while the
   raw cell taken for the corrected value ("C = 1620 / 16", "C = 1620 × 1.5", "(1620 − 10) ×
   (1/2)⁴") is still named. (This pass read "Equivalently" and "subject to" as stating no
   rearrangement; the third pass, item 9, reads the rearrangement before the formula's evaluation
   as a step from the formula whatever words state it.)
9. **The classes closed whole, a third pass** (resumed after the second pass; measured against
   the staged tree before this repair, not only the repaired one). Rule `rearranged-formula` had
   taken a check away: the staged tree failed a wrong rearrangement written with no step word
   ("This rearranges to R = P/V².", "P = V²/R, i.e. R = P/V²", "or R = P/V²", "Equivalently, R =
   P/V².", "Re-arranged: …", "Subject to …, R = P/V².") through the evaluation after it, read as a
   step from it, and once that evaluation was the formula's substitution nothing checked these.
   When rule `rearranged-formula` reads a line as the formula's evaluation, the relation before it,
   in exactly the formula's symbols and in the formula's statement or the next one, is now planned
   as a step from the formula if no step was read for it (`_rearrangement_step`, the formula kept
   per symbol in `_formula_infos`), its reason and `detail` saying "a rearrangement of the formula,
   which the next line evaluates (rule rearranged-formula)"; a correct one holds. A relation the
   prose introduces with the variables swapped for an inverse ("Swap x and y: x = 2y + 1." after "y
   = 2x + 1", `_SWAP_RE`) is no step (it had failed as one on the staged tree too). Rule `part-value`
   takes three more values for a symbol whose every binding stands in another part: a value its
   part's prose states before the line for a quantity named with a word the names of the symbol's
   stated values do not hold (`_prose_named_other`: the label words of their chains or their part's
   question, `_prose_value_name`; "The current in the 6.0 Ω resistor is 1.655 A."; a value named
   only by the stated quantity's words, "The current in it is 1.655 A.", is still not taken), the
   value the answer states for the line's lone head in another part ("V = IR = 1.655 A × 6.0 Ω =
   9.93 V" in part (d), V = 9.9 V in part (c)), and a computation of values with units written in
   the symbol's place, read for the symbol as a value the request gives is (`_computed_in_line`:
   "P = I²R = (9.93 V ÷ 6.0 Ω)² × 6.0 Ω"; the line's arithmetic is checked). Rule `bound-relation`
   leaves unread a relation the prose gives as the value of the quantity its part's question asks
   for, every word of the name a word of the question, when one of its symbols has its stated
   values only in other parts (`_equation_of_asked_quantity`: "The power in the 6.0 Ω resistor is
   9.93 V × I = 16.4 W." as part (d)'s answer had failed against part (b)'s I, a false error the
   rule itself had introduced), and reads a symbol written as applied ("k(0.20)²") as a function
   only where the answer or the request defines it as one (`_defines_function`: "C(x) = 40 +
   2.5x"), so "The energy is ½k(0.20)² = 1.0 J." names k (ST-UNDEC-002). Rule
   `adjacent-restatement` reads no restatement of an earlier chain for a value after the cue whose
   own statement states before it another value of its kind that the chain did not compute
   (`_own_value_before`: "The measured rate at t = 0 h is 1620 counts min⁻¹, so the corrected rate
   is 1600 counts min⁻¹." had been set against "… = 100 counts min⁻¹"), nor for a value followed by
   "of it" ("So 4.4 W of it is lost as heat in the wires.", `_PART_OF_IT_RE`). Rule `rounding-cue`
   reads a value the prose restates in the same unit right after a value it states, after ", so",
   ", which is", ", or", ", i.e." or ", that is", with a stated rounding (`_rounded_prose_values`:
   "The power is 16.4 W, so 17 W to 2 s.f." had passed), its `detail` saying "against the value the
   prose states right before it". Rule `processed-data` leaves unread a ratio of the raw cell to its
   processed value ("1620/1600 = 1.0125") and a line whose own words name the raw quantity by the
   word of the column's name that sets it apart and not the processed quantity ("The measured rate
   fell by 1620 − 820 = 800 counts min⁻¹", "The mean of the first two measured rates is (1620 +
   1151)/2"). Rule `prose-conversion` reads a value restated after "to", "into" or "in" and its own
   unit, then "gives", "is", "equals" or "makes" (`_PROSE_TO_UNIT_RE`: "Converting 55.0 cm³ to dm³
   gives 0.0550 dm³.", "55.0 cm³, which in dm³ is 0.0550 dm³"). And a ratio set against a number
   ("4.0 : 6.0 = 0.67"), which was read but neither checked nor named, is named ST-UNDEC-001 (a
   ratio given a name or set against a ratio is read as before).

On every recorded round-7 STEM answer and on the 558 labelled corpus items, the new readings plan
nothing and change nothing (every check and finding as before, compared byte for byte with the
staged tree before this repair). Remaining limits, stated: a law stated only in a form with no
lone symbol ("V² = PR" with no "P = V²/R") and then evaluated with values the line writes is read
as a step from it under the values the answer states earlier; a reused symbol whose value its
part's prose names only by the stated quantity's words ("The current in it is 1.655 A.") is set
against its stated values, and so is a single value that no statement of its part gives ("P = VI
= 9.93 V × 1.655 A = 16.4 W" as part (d)'s first line fails against part (b)'s I); a reused
symbol whose value is another result of its part of the same dimension (the 4.0 Ω branch's
current used for the 6.0 Ω resistor) holds by rule part-value, and a computation written in its
place is read for it whatever it computes; a relation given as a quantity's value whose numeric
side is a result its part already states, in a reused symbol ("The battery's power output is 12 V
× I = 16.4 W."), or that gives its part's asked quantity, is no claim the branch reads; a value
restated with a rounding in another part than its chain's is not read; a rearrangement written
with no step word and no evaluation of the formula after it is not read (a formula is out of
scope); a value after "so" or "therefore" that opens a new clause with the last chain's dimension
("Therefore 2 W is wasted.") is still read as restating it; and a maths run after another verb
("The battery delivers 12 V × I = 60 W.") names no quantity as its value and is not read.

## 26. STEM repair 6: readings added after the sixth independent test

A sixth independent test planted STEM faults on copies of the round-7 answers and found four
problems: a Given written in prose had neither a check nor an ST code ("Data: emf 15 V, internal
resistance 0.50 Ω.", "Given: the mass of seeds is 12 g.", "Given: mass of seeds: 12 g.", "Given:
15.0 cm³ of acid.", "We know the mass of seeds was 12 g."), while the pack said every Given value
has its check or ST-UNDEC-003, so an agent's true `finding_missing` was refuted; a symbol reused in
a part passed with any value the request states ("P = (9.93 V)² / 4.0 Ω" and "/ 0.50 Ω" in the part
that asks for the power in the 6.0 ohm resistor: ENTAILED, R silently dropped from the check); a
unit written after a fraction was read as the divisor's only, so the recorded answer's own notation
"k = (ln 2)/8 h⁻¹ = 0.0866 h⁻¹" and "The rate is 1/40 s⁻¹ = 0.025 s⁻¹" got a false ST-DIM-001; and
NAND, NOR and XNOR were outside the Boolean grammar (a correct gate and a wrong one got the same
ST-PARSE-001, a truth table ST-UNDEC-001). Each reading is fixed where it went wrong, for its whole
class, with a clean control for every new reading (`tests/stem/test_stem_repair6.py`); the
overseer's side is `docs/OVERSEER_DESIGN.md` section 37. The original translator's English, History
and generic readings are untouched. No ST code was added.

1. **Rule `prose-given`** (`document._prose_given_part`, `_GIVEN_LIST_RE`, `_GIVEN_CLAUSE_RE`,
   `ProseValue.given`; `relations._givens`, `_given_item`, `_prose_condition`). A statement whose
   head, after a list marker or a part label, is "Given", "Data", "Known" or "We know" and ends with
   a colon within three more words ("Data:", "Given:", "Known values:", "We know:", "Given (from the
   question):") is a data list: every value its prose gives a quantity is a Given value, and so is
   every value of the list a line "Given:" opens. A statement that begins "Given", "Known" or "We
   know" with no such colon is a Given clause: the values of its first clause, up to the first
   comma, semicolon or colon, are Given values ("We know the mass of seeds was 10 g."; in "Given that
   the emf is 12 V, the current is 4.1 A." the current is the statement's own result). "Data" with
   no colon heads no Given clause ("Data analysis rewards …"). A prose Given is named by its item's
   words: those before it from the last comma, semicolon, colon, bracket or "and", with the words
   that open the statement or join the name to the value left out ("emf", "internal resistance",
   "mass of seeds"; after a copula the words after it, "each value is the mean of 4 repeats" naming
   the mean), and another value of the item ending the name ("emf 12 V internal resistance 0.40
   Ω"); a value written first is named by the words after it ("15.0 cm³ of acid": acid). A value
   right after "at", "when", "whenever" or "if" is the condition another value of the item is
   stated under, never a Given, and a value stated under one in its item ("the oxygen uptake at 30
   °C is 85 mm³ per g per hour") is set against the supplied table's row as before. An uncertainty
   written "±0.5 °C" or "+/-0.5 °C" in prose takes the unit written after it (the prose reads the
   number alone). The value is then read as the same Given written with "=": against the request's
   value of its symbol, its kind or its dimension (rule given-kinds, rule supplied-values, rule
   given-uncertainty, rule value-at), or, when the request names a quantity by words that all stand
   in the Given's name, against that quantity's value (rule named-given: "Data: emf 12 V, internal
   resistance 6.0 Ω." fails against the internal resistance 0.50 ohm though the request states a
   6.0 ohm resistor); a Given of a kind the request states no value of is named ST-UNDEC-003, so
   every Given value has its check or its ST code. Its reason and `detail` say "rule prose-given". A
   value after a currency sign ("principal €4000") or after a digit group and a space (the "000" of
   "4 000 euros", whose first group is named ST-PARSE-001 as in the "=" form) is never read, and the
   request's own prose is never a Given. Before, `_givens` read only the values a Given statement
   gives with "=".
2. **Rule `part-given`** (`relations._given_in_another_part`, `_part_question_values`,
   `_part_stated_before`, `_part_question_spans`, `_substitution`, `Relation.part_given`;
   `checks._sub_pairs`). A symbol whose every binding stands in another part, substituted with a
   value the request states with its dimension, is read for the symbol in that part with no check
   (as before) when the part's question states that value ("the power dissipated in the 6.0 ohm
   resistor": 6.0 Ω), when the part's question states no value of that dimension (nothing says
   which of the request's values the part uses), or when the part's working states it before the
   line ("For comparison, the 4.0 Ω resistor dissipates P = (9.93 V)² / 4.0 Ω"). When the part's
   question states other values of that dimension and neither it nor the working before the line
   states this one, the substitution of that symbol is a check of its own, at warning severity
   (which of the request's values the symbol stands for there is a reading): the symbol against its
   stated values, the values the part's question states and the readings of rule part-value; its
   reason names rule part-given and its `detail` says "rule part-given: R reused here for a value
   the request gives; its part's question states 6.0 ohm, which it matches too". A symbol checked
   against its bindings in the same line keeps its own check at error severity, so a reading never
   lowers another check's severity. "P = (9.93 V)² / 4.0 Ω" and "/ 0.50 Ω" in that part now fail
   (INT-SUBJ-004 on the receipt), and so does a current computed there with the other resistor
   ("I = V/R = 9.93 V / 4.0 Ω = 2.48 A"); a value the request does not state is set against the
   bindings at error severity, as before.
3. **Rule `fraction-unit`** (`relations.fraction_unit_node`, `_compact_slash`,
   `_pure_factor_dimension`, `_fraction_texts`, `_Planner._fraction_units`,
   `Relation.fraction_units`; `checks.build_check`). A unit written right after a fraction whose
   slash has no space on either side ("1/40 s⁻¹", "(ln 2)/8 h⁻¹"), whose divisor is a numeral with
   that unit and whose dividend carries no unit and names no quantity, may be the divisor's or the
   whole fraction's. An operand of a chain is read with the fraction's own unit ((1/40) s⁻¹) when,
   its bare numbers read as pure factors, that reading gives it the dimension of every neighbour in
   the chain whose dimension is known, and the divisor's reading does not; the relation is then
   checked so, its `detail` saying "the unit written after '1/40 s⁻¹' is read
   as the fraction's own, the reading under which the two sides have one dimension (rule
   fraction-unit)", and rule bare-factor raises no ST-DIM-001. A slip after such a fraction
   ("0.0966 h⁻¹", "0.25 s⁻¹") fails its arithmetic; ST-DIM-001 is raised only when neither reading
   agrees ("1/40 s⁻¹ = 0.025 m"); a spaced slash ("1 / 0.087 h⁻¹ = 11.5 h⁻¹") or "÷" divides by
   the whole operand after it, its unit included, and a divisor's unit that agrees ("0.693/8.0 h =
   0.087 h⁻¹", "t = 0.693/0.087 h⁻¹ = 8.0 h") is kept. Integer-vector dimension arithmetic decides
   which reading a relation takes; nothing is evaluated. Before, the SI form "λ = (ln 2)/8.0 h⁻¹ =
   2.4 × 10⁻⁵ s⁻¹" also failed its arithmetic and its substitution (the divisor's reading, two
   INT-SUBJ-001 errors on correct work) beside the ST-DIM-001.
4. **Rule `boolean-gates`** (`lexer._BOOL_WORDS`, `_GATE_SYMBOLS`; `boolean.gate_order`,
   `_BoolParser._gate`, `parse_boolean`, `parse_truth_table`). With `cs`, the words NAND, NOR and
   XNOR, the Sheffer stroke ↑ or ⊼ (NAND) and the Peirce arrow ↓ or ⊽ (NOR) are Boolean
   operators, read as the negations of AND, OR and XOR (NOR at OR's precedence, XNOR at XOR's, NAND
   at AND's, NOT binding tighter than every one: "NOT A NAND B" is ¬(¬A ∧ B)), in identities,
   evaluations under the values the statement gives and truth tables alike. Their order beside
   another binary operator is no standard, and NAND and NOR are not associative: a bracket level
   (a bracket, an overline group or the whole) that holds a gate beside any other binary operator
   (implicit AND, "+", "·" and "*" included), or two NAND or two NOR, has two readings, and the
   expression is named ST-PARSE-002 ("a Boolean expression with two readings: …"; a truth table's
   output column likewise), never read one way; a chain of XNOR alone is associative and read.
   Before, the arrow ended the maths run, so "A ↑ B = NOT (A AND B)" was read from B. An arrow outside
   computer science, and a lower-case "nor" anywhere, is no gate ("T ↑", "neither … nor …").

On every recorded round-7 STEM answer and on the 558 labelled corpus items, the new readings plan
nothing and change nothing (every check and finding as before, compared byte for byte with the
staged tree before this repair). Remaining limits, stated: a value in a Given statement after "when
the emf is" or "at a temperature of", not right after the condition word, is read as a Given, as
the same value written with "=" is ("Given: I = 4.1 A when ε = 15 V" checks the 15 V); a condition
written after the value it conditions ("Given: oxygen uptake 85 mm³ per g per hour at 30 °C") is not
read as its condition, and the value is named ST-UNDEC-003 as in the "=" form; a reused symbol
given a request value in a part whose question states no value of its dimension is read with no
check; a unit after a compact fraction is re-read only when the divisor's reading disagrees with a
neighbour and the fraction's agrees; the gates are read only where AND, OR, NOT and XOR are
(computer science, upper-case words or the symbols); and a symbol a chain gives a closed expression
and then its value in SI ("k = (ln 2)/8 h⁻¹ = 2.41 × 10⁻⁵ s⁻¹", or "(ln 2)/(8 h)") is bound to the
SI value only, so a later substitution of the expression's value in the first unit with no unit
written ("T = ln 2 ÷ ((ln 2)/8)") fails, as it did before this repair.

## 27. STEM repair 7: readings added after the seventh independent test

A seventh independent test planted STEM faults on copies of the round-7 answers and found three
problems. A law written with the symbol it evaluates not on its own, its evaluation on the next
line, was read as an algebra step from the law (ph-t13: "ε = I(R + r)" then "I = 12 V / 2.9 Ω =
4.1 A"; ph-p7b: "T½ = ln 2/λ, so λT½ = ln 2" then "λ = 0.693/8.0 h = 0.087 h⁻¹"), decided exactly
with the law's other symbols pinned to values from anywhere in the answer (R = 6.0 Ω from part
(d): the engine's r = 120/29) and a rounded constant read as exact (0.693 for ln 2: r =
693/8000), so correct working failed (INT-SUBJ-001), the overseer agreeing with the receipt.
Derivatives written with primes on a letter other than f, g or h applied to a bracket ("v'(t)",
"v′(t)", "v'(1)") or in Leibniz notation beyond the first-order forms of a few letters
("d²v/dt²") were read as products of symbols (v′·t, d²·v/(d·t²)), with neither a check nor an ST
code, while the pack and the gap analysis said ST-UNDEC-001 names a derivative. And a value
restated with a rounding finer than the chain's stated value ("To 3 s.f., V = 9.90 V." or "To
three significant figures, V = 9.94 V." after "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", whose
arithmetic gives 9.93) was set against the stated 9.9 V with both half-widths and passed. Each
reading is fixed where it went wrong, for its whole class, with a clean control for every new
reading (`tests/stem/test_stem_repair7.py`); the overseer's side is `docs/OVERSEER_DESIGN.md`
section 38. The original translator's English, History and generic readings are untouched. No ST
code was added.

1. **Rule `solved-law`** (`relations._solve_for`, `_occurrences`, `_formula_words`,
   `_Planner._solved_law`, `_step_cues`, `_link`, `_sequence`, `_substitution`,
   `_evaluated_formula`, `Relation.prior_readings`; `checks._formula_detail`, `_sub_pairs`,
   `_sub_evaluate`). A chain that gives a symbol S a value by a written closed expression, right
   after a law of its part that states S but not on its own (the relation before it, written with
   "=", with another symbol, S having no stated value before the chain), joined to it as the
   sequence reads a step (a step word or connective, the law in the same statement or the one
   before; or adjacent statements each opening its line of working; never an alternative
   after "or", "and" or a comma), evaluates that law solved for S: its first link is read
   against the solved formula exactly as against a
   formula the answer states for S, and no step is read. `_solve_for` isolates S by exact inverse
   operations through sums, differences, products, quotients, signs, square roots and a square
   (whose principal root it takes, as the quantity's evaluation does), S occurring once and at most
   24 operations deep: "ε = I(R + r)" gives ε/(R + r) for I, "λT½ = ln 2" gives ln 2/T½ for λ, "V²
   = PR" gives V²/R for P, "1/R = 1/R₁ + 1/R₂" gives 1/(1/R₁ + 1/R₂) for R, "E = ½mv²" gives √(E/½/m)
   for v. The check's reason names "the law stated in s… solved for 'S' (rule solved-law)" and its
   `detail` "the line evaluates the law stated in s… solved for 'S': S = … (rule solved-law; never
   an algebra step from the law)". A symbol of the law with no binding whose value the answer
   substituted before the line ("T = 2π/ω = 2π/4.0") is set against those substituted values, as
   the step had pinned it, so the reading is never weaker than the step it replaces: "ω = 2πf so f
   = 3.0/(2π)" fails its substitution. In mathematics, when solving took the principal square root
   of a squared symbol, ST-ALG-001 names it unless "±" is written or a domain restriction is stated
   ("A = πr²" then "r = √(50/π) = 3.99"), as for the step it replaces. A Given statement (one
   that begins "Given", "Data", "Known" or "We know", or the list a "Given:" line opens) is
   data: never the evaluation of the law before it nor a step from it ("Given: ε = 12 V." after
   "I = ε/(R + r)" is checked as a Given against the request; it had failed as a step). Read
   as before: a law in which S occurs twice or under a function (a quadratic in S, e^(−λt): an
   equation the line solves, a step and its stated roots), a law with no other symbol ("2x + 3 = 11"
   then "x = (11 − 3)/2"), a value alone after a law whose every other symbol has a stated value
   (its solution: "λ = 0.097 h⁻¹" after "λT½ = ln 2" with T½ stated fails as a step and as its
   stated roots), the formula of S the answer states or its rearrangement (rule
   `rearranged-formula`), and anything the sequence would not read as a step. A value alone after a
   law with another symbol that has no stated value is a value stated for S, with no check ("F =
   ma" then "a = 4.0 m s⁻²"): as a step it failed whatever the value.
2. **Rules `leibniz` and `prime-derivative`** (`parser._leibniz_end`, `_order_marker`,
   `_one_letter`, `_d_letter`, `_LEIBNIZ_ORDERS`, `_Parser._ident`, the LaTeX `\frac` reading). A
   derivative in Leibniz notation: a numerator d with an optional order marker ("²", "^2", "^{2}",
   "**2", or a digit glued on) and one Latin or Greek letter differentiated ("d²v", "d^2y", "dθ"),
   or a glued "dv" or "dN", or d alone with its marker (the operator "d/dx", "d²/dx²"); a
   denominator d and one letter ("dt", "dθ") with the same order marker, orders 2 to 9; in LaTeX,
   `\frac{d^2v}{dt^2}`, `\frac{dN}{dt}` and `\frac{d\theta}{dt}` read as one such form. It is "a
   derivative" (ST-UNDEC-001), the relation not checked. A derivative in prime notation: any one
   Latin or Greek letter with primes written applied to a bracket with no space ("v'(t)", "v′(1)",
   "s″(t)", "θ′(t)"), not only f, g and h; the node keeps the name and the argument, so an
   evaluation "v'(1) = 6 + 6(1)" is set against a formula "v'(t) = 6 − 6t" the answer states and
   fails (the formula itself named ST-UNDEC-001). No derivative: orders that differ ("d²v/dt"), d
   over a symbol that is no differential ("d/t"), a primed letter with no bracket ("v′ = 2.0 m s⁻¹",
   a symbol) or with a space before it ("v′ (t)"). In computer science the Boolean reading of a
   prime is unchanged ("A'(B + C)" is NOT A AND (B OR C) there). Before, each was a product of
   symbols, "an equation in an unknown", with neither a check nor an ST code.
3. **Rule `finer-restatement`** (`relations._computed_operand`, `_Planner._finer_restatement`,
   `Relation.finer`; `checks._res_finer`). A value restated with a rounding the prose states and
   set against a chain's final value (rule `rounding-cue` for a value stated for a symbol, "To 3
   s.f., V = 9.90 V.", "V = 9.94 V (3 s.f.)"; a prose restatement after a cue, ", so 9.95 V to 3
   s.f.", "To 3 s.f., the terminal potential difference is 9.94 V.") whose own half-width (the
   stated rounding's, never less than half a unit in its last written digit; in the chain's unit by
   exact factors when the units differ) is smaller than the half-width of the chain's final value
   states figures that value does not carry. Beside the rounding-cue check, which is unchanged, it
   gets a check against the value the expression the chain's last "=" evaluates gives (the operand
   before the stated value, closed and read one way), with that half-width alone and τ = 0, its
   numerals read as written arithmetic reads them (a carried result or a written constant over its
   interval), at warning severity: that the restated value is the line's arithmetic as written is a
   reading the answer did not state (it may have computed with figures its working does not show).
   "To 3 s.f., V = 9.90 V." and "… 9.94 V." fail it (INT-SUBJ-004), "… 9.93 V." holds; "To 4 s.f.,
   P = 16.34 W." after "P = (9.93 V)² / 6.0 Ω = 16.4 W" fails it and the rounding-cue check too.
   Nothing is added when the rounding is no finer than the chain's value, the chain writes no closed
   expression before its value, or the two units cannot be compared by exact factors.

On every recorded round-7 STEM answer and on the 558 labelled corpus items, the new readings plan
nothing and change nothing (every check and finding as before, compared byte for byte with the
staged tree before this repair). Remaining limits, stated: rule solved-law reads only the law
right before the line, in its part, joined to it as a step would be, and a law in which the
symbol occurs twice or under a function is read as before; a value alone after a law with another
symbol that has no stated value is unchecked; a derivative written as a primed letter with no
bracket ("y'' = 6"), in Newton's dot notation ("ẋ = 3") or with ASCII digits glued on ("d2y/dx2",
named ST-PARSE-001 as a relation sign no maths span reads, as before) is not named a derivative,
and outside computer science a complement written with a prime before a bracket ("A'(B + C)") is
named a derivative, unchecked (before, it was silent); differentiation itself stays outside the
encodings (the translator gap `formulas-derivative`); a restatement whose prose names its quantity
with a dotted abbreviation ("the terminal p.d. is 9.94 V") is not read, before or after; and a
prose value with a stated rounding that names another quantity of the chain's dimension ("To 2
s.f., the emf is 12 V." after the terminal potential difference's chain) is set against the last
chain and fails (INT-SUBJ-001), exactly as on the staged tree before this repair.

## 28. STEM repair 8: readings added after the eighth independent test

An eighth independent test planted STEM faults on copies of the round-7 answers and found four
problems. A value a run computes under a condition ("Mean time at 30.0 °C = (33.1 s + 34.0 s +
32.5 s) ÷ 3 = 33.2 s", "Rate at 20.0 °C = 1/61.7 s = 0.0162 s⁻¹", "I at t = 5 s = 12 V / 4.5 Ω =
2.7 A", "The corrected rate at t = 40 h = …", "Uptake at 30 °C = 2 × 40 = 80", "Speed after 2.0 s
= …") or right after a list that names it ("Mean of 18, 27 and 40 = (18 + 27 + 40) ÷ 3 = 28.3")
was read as a relation between the condition (or the list's last value) and the computation, and
failed (INT-SUBJ-001 on correct working, four of them with ST-DIM-001), the overseer agreeing with
the receipt. A value copied wrongly from the supplied table ("t = 12 h: 568 − 20 = 548 ± 11", the
table states 586; 1115 for 1151; 330 for 303) and a wrong background ("220 − 25", the supplied
text states 20) were neither checked nor named, while the pack's D31 said a value the working takes
from the table is set against its row. A law stated right before a line that evaluates it in
another shape ("(c) [1] V = ε + Ir" then "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V") was named by
nothing, and a failed substitution of a law ("P = V/R" then "P = (9.93 V)² / 6.0 Ω = 16.4 W") named
the line and the value it contradicts but not the law. And a rounding restated after ", so" with a
word between it and the chain's value ("= 60.4% decrease, so 61% to 2 s.f.") was not read. Each
reading is fixed where it went wrong, for its whole class, with a clean control for every new
reading (`tests/stem/test_stem_repair8.py`); the overseer's side is `docs/OVERSEER_DESIGN.md`
section 39. The original translator's English, History and generic readings are untouched. No ST
code was added.

1. **Rule `value-at` for a computing chain** (`relations._VALUE_AT_RE`, `_Planner._value_at`,
   `_computed_at`, `_value_at_chain`). A maths run right after a condition word ("at" and "when"
   as before, and now "after", "before", "during", "within", "until", "for" and "in": the words that
   state a time or an extent a value holds under; never a word that joins an operand written in
   words, "by", "over", "of", "to", "from", rule `fragment`) that opens with the condition and then
   computes the named quantity's value (a written closed expression with no symbol after the
   condition, every link after it "=" or "≈") states that quantity's value under the condition: the
   condition binds nothing and is no side of a relation, the run's links after it are checked as in
   any chain, and the value the chain states last is a computed final value (a restatement of it is
   read as of any chain's). The condition and the computation must be values of different kinds, as
   for a stated value (rule value-at: the value the chain states last against the condition, or,
   with none stated, the expression's own dimension), so a conversion of the condition ("T at 25
   °C = 25 + 273 = 298 K") is read as before.
2. **Rule `condition-value`** (`_Planner._condition_value`; `checks._GIV_RULES`, `_giv`). In a run
   read by rule 1, when the computation takes exactly one value of the condition's dimension (by its
   written unit; one value written twice counts once), that value stands for the condition: a `giv`
   check sets it against the condition's value, in SI, every written digit counting on both sides
   (rule given-digits: "in 10 s" against "× 20 s" no longer holds by the trailing zeros), at warning
   severity ("which value of the run's computation stands for the condition the run is stated under
   is a reading"). "The charge that flows after 2.0 s = 4.1 A × 3.0 s = 12.3 C" fails (INT-SUBJ-004).
   Nothing is read when the condition has no unit, is a percentage or has no exact SI value (an
   affine unit: "at 30 °C"), or when the computation takes no value, or two values, of its
   dimension ("× (4.0 s − 1.0 s)").
3. **Rules `name-list` and `item-label`** (`relations._NAME_LIST_RE`, `_LIST_TAIL_RE`,
   `_list_values`, `_ITEM_LABEL_RE`, `_name_head`, `_Planner._named_value`, `_list_terms`,
   `_additive_groups`). The prose right before a run that ends with a list or a range of values
   ("Mean of 18, 27 and ", "Difference between 40 and ", "The rise from 20.0 °C to ", "Mean of 18
   mm³, 27 mm³ and ") makes the run's first value the list's last item, part of the quantity's
   name, when the run goes on to compute (a written expression after its first "="): "Mean of 18, 27
   and 40 = (18 + 27 + 40) ÷ 3 = 28.3" is the mean's value, its arithmetic checked. A list with no
   computation after it ("… 18, 27 and 40 = 28.3") stays a relation written partly in words (rule
   fragment, ST-PARSE-001). The noun of a numbered item ("trial", "run", "repeat", "sample", "day",
   "year", "step", "stage", "reading", "term", "generation" …) before a run whose first operand is a
   whole number written with no point makes that number the item's ("Time for trial 2 = 60.8 s",
   "Year 2 = 4000 × 1.036² = 4293.18"): nothing is checked for the number. Rule name-list's check:
   in a run so read, each sum or difference of the computation that takes a listed value (as
   written) has its other terms set against the list's values, as written, every digit counting, at
   warning severity ("which of the values the prose lists the computation's value stands for is a
   reading"): "(18 + 27 + 41) ÷ 3" fails; a term that is a listed value, 100 or 1000, or a
   computation that takes none of them ("85 ÷ 3", the sum carried), plans nothing.
4. **Rule `table-terms`** (`_Planner._table_operands`, `_table_terms`, `_table_quantity_values`,
   `_computed_at_row`; `checks._GIV_RULES`). In a line read by rule table-operands (its rows named by
   the line, else by its part's question, and one column read), the terms of each sum or difference
   of the working that holds a value of the column's quantity (a cell, a value the request or its
   supplied texts state for that quantity outside the table, or, the whole computed side, when the
   line states its value with the column's unit) are the values the working takes of that quantity;
   a term that is none of them, as written, is read. When the line takes the cell of every named row
   but one and exactly one such term, the term is that row's value copied wrongly: it is set against
   the row's cell ("t = 12 h: 568 − 20 = 548 ± 11" against 586; "(9.6 − 3.9) ÷ 9.6 × 100" against
   site C's 3.8). When it takes the cell of every named row, the term is set against the values
   the request and its supplied texts state for the quantity outside the table ("220 − 25" against
   the background of 20 counts per minute; a bare term is read in the column's unit), unless the
   line computes a cell or such a value itself ("566 + 20 = 586", "586 − 566 = 20") or the term is a
   stated percentage of the cell (a bound, rule processed-data's reading: "586 + 11.72"). Each is a
   `giv` check at warning severity, every written digit counting; nothing is read when two terms or
   two rows' values are unaccounted for, a term carries a unit of another dimension, the quantity
   has no unit and no value of it is stated outside the table, or the wrong value is a factor ("2 ×
   41"). Two row readings of rule table-operands changed with it: a named row whose cell the line
   states as its own value is the row of the line's result, never a row its working takes a value
   from ("Uptake at 30 °C = 2 × 40 = 80": the 40 had been set against the 30 °C row's 80, a false
   INT-SUBJ-004 on correct working), and so is the row a run's condition names (rule 1) when the
   working takes a cell of the column and not that row's ("Uptake at 30 °C = 2 × 40 = 90": its
   arithmetic fails, and the 40 is not set against the 30 °C row). The same repair makes a value
   the prose states for a quantity the request names by its words (rule named-given) restate the
   request's data as written, every digit counting: "the background count rate of 25 counts min⁻¹"
   had held against the supplied 20 counts per minute by the 20's trailing zero.
5. **Rule `law-values`** (`relations._orders`, `_power_of`, `_law_dims`, `_Planner._law_values`,
   `_another_relation`, `_evaluated_formula`, `_sub_or_equation`, `_link`, `_chain_ctx`;
   `checks._TITLED_WARNINGS`). A line that gives a symbol a value right after its part states a law
   for it (the formula the scope holds for the symbol, stated in the same part), whose written
   expression neither repeats the law's shape (no substitution pairs a symbol with each value) nor
   can be evaluated under its symbols' stated values (a symbol with no stated value: ε), and also
   the same law and its evaluation written in one line ("V = ε + Ir = 12 V − (4.14 A × 0.50 Ω) =
   9.9 V"): the line's values with units (distinct by value and unit) are paired with the law's
   symbols, one value for each symbol and every value used, at most five, so that each symbol whose
   dimension is known (from its stated values, or from the law itself by exact exponent arithmetic:
   every term of a sum has the sum's dimension, a factor or a divisor whose partner's dimension is
   known the one that makes the product's, `_law_dims`) gets a value of that dimension and the law
   at those values has the dimension of the value the line states. Several pairings are read only
   when they give one exact value (the current and the resistance of "Ir" either way). The law at
   the paired values is set against the value the line states, under the tolerance rule: an `eq`
   check titled "the law stated in s… at the values the line puts in", its statements the law's and
   the line's, its reason naming every pairing and "rule law-values", at warning severity ("which of
   the line's values stands for which symbol of the law is read from their dimensions, a reading the
   answer did not state"). "V = ε + Ir" gives 14.07 V where the line states 9.9 V: it fails, while
   the line's arithmetic holds. Nothing is planned in the request, for a link other than the line's
   first, for a law of another part, one with a parameter, a ±, a function or notation outside the
   encodings, a dimensionless symbol, a line whose values do not stand one for each symbol ("V = 12
   V − 2.07 V = 9.93 V"), when no pairing (or more than one value) agrees with the dimensions, or
   when the line states the value itself ("F = 2 × k = 6 N"). Found closing it, the reading of a
   formula whose shape the line does not repeat as the formula under its symbols' stated values
   (`_evaluated_formula`, "a = 6 − 6(1)" after "a = 6 − 6t") now skips a line that takes a value of
   a dimension no symbol of the formula has, nor a power of one, every symbol's dimension known: "P
   = 9.93 V × 1.655 A = 16.4 W" right after "P = V²/R" evaluates P = VI, and had been set against
   V²/R under the stated values and failed (INT-SUBJ-001 on correct working).
6. **A failed substitution names its law** (`relations._related_statements`). The statement of the
   formula a substitution evaluates comes first among the statements the check relies on, when
   another statement of the answer states it (not the request), so a failure names the law's claim
   beside the line's and those whose values it contradicts ("P = V/R" then "P = (9.93 V)² / 6.0 Ω =
   16.4 W": s4.3, s4.2 and s3.2). Only the claim ids of a failure finding change; a passing check is
   unchanged.
7. **Rule `inline-restatement` with describing words** (`relations._INLINE_WORD`,
   `_INLINE_RESTATE_RE`). Up to three words that say what the value is may stand between a chain's
   value and the comma before the restatement's cue ("= 60.4% decrease, so 61% to 2 s.f.", "=
   9.93 V across the resistors, so 9.8 V to 2 s.f.", "= 4787.58 euros, so 4787 euros to the
   nearest euro"), never a word that opens a clause of its own (a verb, a connective: "so", "and",
   "which", "is", "gives" …). The restatement is checked as any inline restatement: the three fail,
   their right roundings hold.

On every recorded round-7 STEM answer and on the 558 labelled corpus items, the new readings plan
nothing and change nothing (every check and finding as before, compared byte for byte with the
staged tree before this repair). Of the round-7 arena's STEM mutations, one gains a check: the
`stem_substitution` mutation of bi-t13 ("(80 − 70) ÷ 40 × 100 = 100%", 70 in place of the 20 °C
row's 40) is named by its arithmetic as before and now also by rule table-terms (INT-SUBJ-004 on
the same claim). Remaining limits, stated: a conversion of the condition written
with a bare sum ("T = 25 °C = 25 + 273 = 298 K") is read as before (its two links compared as
written); rule condition-value compares a condition with no exact SI value (°C, °F) with nothing;
a list with a single run link ("Mean of 18, 27 and 40 = 28.3") stays ST-PARSE-001; rule
table-terms reads one unaccounted term at a time (two wrong numbers in one line, or a wrong
factor, are not read); rule law-values pairs only values written with units (a bare-number
evaluation is not paired) and reads only the law the scope holds for the symbol in its part; a law
whose symbols have no stated values evaluated in its own shape ("P = V/R" then "P = (9.93 V)² /
6.0 Ω" with V stated nowhere) has nothing to contradict; a product written in another order than
the law's ("V = ε − rI") is paired by position, so its values are introduced for the symbols and
nothing is checked (as before); and a value the prose states for a quantity matches only when every
word the request names it by stands in its name (rule named-given, as before).

## 29. STEM repair 9: readings added after the ninth independent test

A ninth independent test planted STEM faults on copies of the round-7 answers and found eight
problems in the readings and one in the pack. A correct line at the end of a part ("As a check, ε
= 9.93 V + 4.14 A × 0.50 Ω = 12.0 V.", "The lost volts are 4.14 A × 0.50 Ω = 2.07 V.") took the
words of the part's question, so a later change stated from the part's result ("… rises, from 9.9
V to 10.7 V") was set against that line's value: a false INT-SUBJ-004 on correct working, which the
overseer agreed with (rule named-change, STEM repair 1). A Given of a function's value ("Given:
v(1) = 4 m s⁻¹.", the request's v(t) = 6t − 3t² giving 3) and a Given function ("Given: v(t) = 6t −
2t².", "Given: a(t) = 6 − 4t.") had neither a check nor an ST code, while the pack said every Given
has one or the other, so an agent's true `finding_missing` was refuted. A trial copied wrongly into
the mean over a supplied row's trials ("Mean time at 30.0 °C = (33.1 s + 43.0 s + 32.5 s) ÷ 3 = 36.2
s", the cell being 34.0), a wrong rearrangement evaluated for a quantity the request names ("So r =
(ε + V)/I = (12 V + 9.93 V)/4.14 A = 5.3 Ω.", the request's 0.50 ohm), a decay over a stated number
of half-lives divided by the number ("5 half-lives, C = 1600 counts min⁻¹ ÷ 5 = 320 counts min⁻¹"),
a wrong median in any form ("The median of 18, 27, 40, 58, 80, 92 and 61 is 61.", "Median uptake = 61
mm³ per g per hour", "Median of … = 61") and a value restated at a rounding it is not written to ("=
60.4% decrease, which is 60.4% to 2 s.f.", "To 3 s.f. the external resistance is 2.4 Ω.") were
neither checked nor named. Each reading is fixed where it went wrong, for its whole class, with a
clean control for every new reading (`tests/stem/test_stem_repair9.py`); the overseer's side, with
the pack's readability, is `docs/OVERSEER_DESIGN.md` section 40. The original translator's English,
History and generic readings are untouched. No ST code was added.

1. **Rule `part-answer`** (`_Planner._labelled_values`, `_part_answers`, `_names_other_quantity`,
   `_check_cue`, `_own_label_words`, `_items_by_statement`, `_item_of`; `relations._CHECK_CUE_RE`,
   `_question_head`). The words of a part's question label only the value that answers it: the last
   value the part computes, leaving out, from the end of the part back, a line that says it checks
   a value (a check word, "check", "verify", "confirm" and their forms, in the prose right before its
   run, or right after the statement's last run: "As a check, …", "Check: …", "…, which checks"), a
   line whose own words name another quantity (its label, or the prose naming its run's value right
   before it, when those words neither hold every word of the question's quantity, its name up to
   its first preposition, nor are all words of the question: "The lost volts are …" in the part that
   asks for the terminal potential difference) and a line that gives its value to a quantity the
   request names that the question does not (rule 2's reading: "So the emf is …", "ε = …"). A part
   with no such value labels nothing; a part with no question keeps its last value. Rule named-change
   (a change stated from a value) and rule changed-value (the value a change ends at, which a later
   substitution may take) read the labels so: with a check line at the end of part (b), the change
   "from 4.1 A to 2.7 A" is recorded again, and "V = 12 V − 2.7 A × 0.50 Ω" in part (e) no longer
   fails against 4.1 A (a false INT-SUBJ-001 found closing the class).
2. **Rule `named-result`** (`_Planner._named_results`, `_request_quantity`, `_own_label_head`;
   `relations._label_head_words`; `checks._giv`; `document._named_quantities`). The value a line gives
   a quantity the request names (the final value of a chain, computed or stated for a symbol) is
   set against the request's value of that quantity, as rule named-given sets a value the prose
   states: a `giv` check at warning severity ("the answer gives a value to the quantity ('internal
   resistance') the request names; the request's value is matched to it …, a reading the answer did
   not state"), every written digit counting. The line names the quantity by the prose right before
   its value (rule bound-relation's reading: "So the internal resistance is (12 V + 9.93 V)/4.14 A =
   5.3 Ω."), by its label's first words up to a preposition or a comma ("Internal resistance: r = …"),
   or by its lone symbol, when the symbol has no value of its own before the line (no binding in the
   answer or the request) and every value the answer substituted for it before the line is the
   request's value of one named quantity ("V = 12 V − (4.14 A × 0.50 Ω)" put the request's 0.50 ohm
   for r, so "r = (12 V + 9.93 V)/4.14 A = 5.3 Ω" and "So r = 5.3 Ω." give the internal resistance a
   value). Only a value with a unit is read, against the request's values of its dimension; a Given
   statement is set against the request as a Given (rule given-kinds); nothing is read with no
   request (the relay form). The request's reading of the words that name a quantity changed with
   it: the words after a preposition that stands between the name and the words before it are the
   name ("a battery of emf 12 V" names the emf, where it had named "battery emf", so "the emf is 9.0
   V" matched nothing), and a preposition and an article right before the value open a noun phrase
   whose name follows the value, so the words before name nothing of it ("the horizontal component of
   a 10 N force" had named the 10 N "horizontal component", a false alarm on a correct component
   found closing the class).
3. **Rule `given-function`** (`_Planner._given_functions`, `_request_functions`,
   `_request_function_unit`, `_given_function_value`; `relations._applied_value`, `_glued_bracket`,
   `_function_definition`; `checks._TITLED_WARNINGS`, `_eq`, `_step`). A Given statement that gives a
   function's value restates the request's data too: the request's function of that name at the
   Given's argument (any number, however written: "v(1)", "v(1/2)", "v(−1)", "v(2 − 1)") against the
   Given value, an `eq` check the engine evaluates, every written digit of the Given counting and τ
   = 0, in the unit the request's prose states for the function's values ("Its velocity, v m s^-1"),
   compared in SI ("Given: v(1) = 300 cm s⁻¹." holds), or as written for a Given with no unit. A
   Given function ("Given: v(t) = 6t − 2t².", "Given: v(t) = 4.", and "Given: v = 6t − 2t²." for a
   function the request defines) is set against the request's function, its variable renamed, for
   every value of the variable: an `alg` check from the trivially true premise, as rule antiderivative's.
   Both at warning severity ("that the Given restates the request's function is a reading"). A Given
   of a function the request does not define, at an argument that holds a symbol ("Given: v(t + 1) =
   4 m s⁻¹.") or a unit ("v(1 s)"), with a unit of which the request states none, or of another
   dimension, for the function's values, or a Given function written with a unit or with symbols
   other than its variable, is ST-UNDEC-003, named with why. f, g or h applied to a number are
   applications in the grammar, so their Given ("Given: f(2) = 6.") is checked as the written
   arithmetic of the request's function applied, as before. A Given of a function's value is no
   equation in its letter: it is never the relation a later line is a step from ("Given: v(1) = 3."
   read as v·1 = 3 had made the correct "v(2) = 6(2) − 3(2)²" a failing algebra step, a false
   INT-SUBJ-001 the staged tree already gave, found closing the class) and no equation whose roots
   follow.
4. **Rule `row-terms`** (`_Planner._row_terms`, `_table_operands`; `relations._repeat_columns`,
   `_REPEAT_NAME_RE`; `checks._GIV_RULES`). A supplied table's columns that write one quantity
   repeated (names that differ only by a trial's, a repeat's or a run's number, one unit: "Time,
   trial 1 / s" to "Time, trial 3 / s") are the repeats of each row. In a line that names one row
   (its line, a run's condition, or its part's question), each sum or difference of the working that
   takes a cell of that row's repeats has its terms read: a cell of the repeats in another row is set
   against the named row's repeats ("(33.1 s + 17.6 s + 32.5 s) ÷ 3", the 17.6 being the 40.0 °C
   row's), and a term that is no cell of the repeats, when it is the only one and exactly one repeat
   of the row is taken nowhere, is that repeat copied wrongly and is set against it ("(33.1 s + 43.0 s
   + 32.5 s) ÷ 3" against 34.0). Each a `giv` check at warning severity, the data taken as written;
   the row's trials in any order hold, and two unaccounted terms are not read.
5. **Rule `decay-law`** (`_Planner._half_lives`, `_decay_law`). After the prose states a number of
   half-lives, when no power of ½ follows in its statement, the value the statement goes on to
   compute from exactly one value of the stated value's dimension (the value before the decay) is
   set against the decay law over that number, that value × (½)ⁿ: an `eq` check at warning severity
   ("the number of half-lives is read from the prose, and the value before the decay is the one value
   of the result's dimension the line takes"). "C = 1600 counts min⁻¹ ÷ 5 = 320 counts min⁻¹" after
   "5 half-lives" fails (the law gives 50); "÷ 32" and "÷ 2⁵" hold. A power of ½ is left to rule
   half-lives, which sets its exponent against the number, as before.
6. **Rule `statistics`** (`_Planner._statistic_run`, `_statistics_prose`, `_plan_statistic`;
   `relations._STAT_COMPUTED`, `_STAT_RE`, `_STAT_LIST_RUN_RE`, `_STAT_LIST_PROSE_RE`,
   `_STAT_COLUMN_PROSE_RE`, `_exact_num`). A statistic stated for the values the prose lists ("The
   median of 18, 27, 40, 58, 80, 92 and 61 is 61.", "Median of 18, 27, 40, 58, 80, 92 and 61 = 61",
   "Mean of 18, 27 and 40 = 28.3") or for the supplied table's column its words name, with no row
   named ("Median uptake = 61 mm³ per g per hour", "The median uptake is 61 mm³ per g per hour.") is
   formed by the STEM pack from the values as written (the median by ordering them, the middle one or
   the mean of the middle two; the mode by counting them, one value occurring most often, more than
   once; the range as the largest minus the smallest; the mean as their sum over their count) and the
   stated value is set against it: an `eq` check at warning severity, the comparison the engine's
   under the tolerance rule. A standard deviation, a variance, a quartile, a percentile or an
   interquartile range, and a mode the values do not have as one value, are ST-UNDEC-001, unchecked.
   Before, the list's last value was read as a side of a relation ("61 = 61", which held), or the
   relation as written partly in words (ST-PARSE-001: "Mean of 18, 27 and 40 = 28.3", which section 28
   left so); a list named by a word that is no statistic ("Sum of 18, 27 and 40 = 85") still is, and a
   row's value ("The mean uptake at C is …") is no column's statistic.
7. **Rule `rounded-digits`** (`_Planner._rounded_digits`; `relations._exact_place`, `_show_place`).
   A value stated with a rounding the prose states for it (a restated result read by rule
   rounding-cue, a value the prose states after a copula with a rounding in its clause, a value
   stated for a symbol with one) is written to that rounding: the place the rounding keeps ("to 2
   s.f." of 60.4 keeps the units, "to 3 s.f." of 2.4 the hundredths, "to the nearest cent" the
   cents) is set against the places the value is written to (its last written digit's; a whole
   number's trailing zeros may stand for it, so "60" is written to the units or to the tens), an `eq`
   check, exact, at warning severity ("which value the rounding the prose states is of is read from
   the prose, and the place a value is written to from its numeral"). "= 60.4% decrease, which is
   60.4% to 2 s.f." and "To 3 s.f. the external resistance is 2.4 Ω." fail; "60% to 2 s.f.", "2.40 Ω to
   3 s.f." and "4780 to the nearest ten euros" hold. Before, a value restated at a stated rounding
   without being rounded passed: the rounding-cue check sets the value against the chain's within the
   rounding's half-width, which an unrounded value always meets.

On every recorded round-7 STEM answer and on the 558 labelled corpus items, the new readings plan
nothing and change nothing (every check and finding as before, compared with the staged tree before
this repair). Remaining limits, stated: rule part-answer recognises a check by its words, so a check
line with no check word that names no other quantity still answers its part; rule named-result reads
a symbol only when every value substituted for it before the line is one named quantity's; rule
given-function reads a Given of f, g or h applied to a number as written arithmetic (an error when
it fails, not a warning); rule row-terms reads one unaccounted term, and only in a line that names
one row; rule decay-law reads only the statement that states the number of half-lives; rule
statistics forms only the four statistics named, from at least two values, and reads a column only
when its words name exactly one; and rule rounded-digits reads only the rounding phrases rule
rounding-cue reads, for the values listed above (a rounding written in any other form is read as
before).


## 30. STEM repair 10: readings added after the tenth independent test

A tenth independent test planted STEM faults on copies of the round-7 answers and found eight
problems. A wrong conversion the prose states with a verb ("A time of 45 s is 0.45 min.") was
checked only when it ended the whole answer: whether the restated value ends its clause was read in a
60-character window of the whole text, which the next statement filled. A line naming its rows and its
column ("The nitrate rise from site A to site D is (8.4 − 1.2) ÷ 1.2 × 100 = 600%.") was read in no
column when its part's question named another. Values at a supplied table's row restated wrongly went
unnamed in common shapes ("Site A has 43 mayfly nymphs per kick sample.", "the most nymphs (43)").
Another resistor's value substituted for the one a sentence names ("The power dissipated in the 4.0 Ω
resistor is P = (9.93 V)² / 6.0 Ω = 16.4 W."), a wrong law evaluated right at a condition its part had
computed ("Using C = C₀ − λt, C = … = 1597 counts min⁻¹ at 32 h.", part (d) having 100 counts min⁻¹ at
32 h), a base conversion in prose ("The binary number 110010₂ is 48 in denary.") and a definite
integral ("∫₀¹ 6t dt = [3t²]₀¹ = 6") were named by nothing (the last ST-UNDEC-001 whatever its value).
A 0.44% slip on a power of the request's exact rate held under τ = 1/100, and a value restated from a
value written with an ellipsis ("= 4787.58…" then "= 4787 euros, to the nearest euro") was
ST-UNDEC-001 whatever its rounding. Each reading is fixed where it went wrong, for its whole class,
with a clean control for every new reading (`tests/stem/test_stem_repair10.py`); closing the classes
found more of each, below. The overseer's side is `docs/OVERSEER_DESIGN.md` section 41. The original
translator's English, History and generic readings are untouched. No ST code was added.

1. **Rule `prose-conversion`** (`_Planner._prose_conversions`). Whether a value the prose restates in
   another unit ends its clause is read in its own statement (`ProseValue.after`, statement-bounded),
   so a conversion followed by another statement, on the next line or the same one, is read like one
   that ends the answer. The class's other windows of the whole text were found and bounded too: rule
   table-data (below).
2. **Rule `table-operands`** (`_Planner._table_operands`). When the words of a line name several
   columns with its part's question, the column is the one the line's own words name, when they name
   exactly one and the line takes a cell of it.
3. **Rule `row-value`** (`_Planner._row_values`, `_row_values_more`, `_row_values_clause`,
   `_value_clause`, `_clause_rows`, `_row_check`; `relations._ROW_NUM_KEY`, `_ROW_AT_KEY`,
   `_row_key_of`, `_column_head_word`, `_names_processed`, `_modifiers_fit`, `_VALUE_CLAUSE_START_RE`,
   `_VALUE_CLAUSE_END_RE`, `_ROW_STATES_RE`, `_ROW_CLAUSE_SKIP_RE`, `_ROW_COMPARE_AFTER_RE`,
   `_ROW_LETTER_MENTION_RE`, `_ROW_NUMBER_MENTION_RE`). The tester's shapes are read (the value after
   "Site A has", a run labelled by the column after the row, "number", "total", "amount to" and "come
   to" as verbs, a column joined to the clause's first, a count the clause leaves its column out of,
   the column before "of" and the row after the value, the column and the row after the value), and a
   column is named by the last word of its counted quantity when no other column's name has it, in
   the singular or the plural. Closing the class found the reading was a list of shapes, each fixing
   the order of the row, the column and the verb, so the clause reading takes what every shape leaves:
   a value its own clause (bounded by its statement and by the words that open another clause) states
   (right after a verb of being or reaching, "has", "of", "=", an opening bracket or an apposition's
   comma, an adverb such as "only" between), naming exactly one row (a site's letter after "site", a
   preposition, as a possessive or as the clause's subject; a number with a numbered table's key unit,
   after the key's symbol and "=" too) and one column, in any order ("Dissolved oxygen was 3.9 mg dm⁻³
   at site C.", "Site C's dissolved oxygen is only 3.9 mg dm⁻³.", "The measured count rate was 568
   counts min⁻¹ at 12 h."). The shapes that name the row after "at" read a numbered row too, a label
   run whose symbol is the label's last word is read with the words before it ("At 12 h, measured
   count rate = 568 counts min⁻¹."), and columns whose names differ only by a number are told apart by
   it ("At 30.0 °C, trial 2 took 43.0 s."). Closing the class also found false failures on correct
   working, each removed at its cause: a value followed by a comparison or an operation ("5.8 mg dm⁻³
   lower than at A", "7 times that at A") is no cell; a clause naming a processed quantity the
   column's name does not ("corrected", "mean", "uncertainty", "background", "change": "The corrected
   count rate at 12 h is 566 counts min⁻¹.") is not read against the raw column; a phrase that names
   a column by a part of its name names it only when the words before that part are words of the
   name, determiners or superlatives ("the decay rate" is no "Measured count rate"); and a value its
   clause states under a condition, a hypothesis, a target or a modal verb, or right after a bound
   ("If nitrate at site B fell to 4.0 mg dm⁻³, …", "A target of 9.0 mg dm⁻³ of dissolved oxygen at site
   C would …", "is below 4.0 mg dm⁻³"), is no value of the row (`_unstated`; the first had failed on the
   staged tree already, through the shape that reads "falls to").
4. **Rule `table-data`** (`_Planner._table_values`, `_table_check`). The words that choose the column
   are the value's own statement's, never a 200-character window across statements (a sentence before
   the line that named another column had left the line unread), and a processed quantity is not read
   against the raw column, as for rule row-value.
5. **Rule `named-change`** (`_Planner._named_changes`). The value a change starts from that the change
   states under a condition of its own ("from 1131 counts min⁻¹ at 4 h") restates no value computed
   under another condition (it had been set against part (d)'s value at 32 h and failed).
6. **Rule `named-component`** (`_Planner._named_components`; `relations._COMPONENT_NOUNS`,
   `_COMPONENT_BEFORE_RE`, `_COMPONENT_AFTER_RE`; `checks._GIV_RULES`). A working whose statement names
   a component by one of the request's values ("the power dissipated in the 4.0 Ω resistor", "the
   current through the 4.0 Ω resistor") and whose values of that dimension are all the request's and
   none the component's is set against the named component: a `giv` check at warning severity.
7. **Rule `condition-result`** (`_Planner._condition_results`; `relations._TRAILING_CONDITION_RE`,
   `_QUESTION_CONDITION_RE`, `_condition_si`; `checks._res`). A value the answer computes for a symbol
   under a condition (stated right after the value, before the run, or by its part's question for the
   part's answer) is set against the value it computed for the symbol under the same condition before:
   a `res` check (R8) at warning severity.
8. **Rule `prose-base`** (`_Planner._prose_bases`, `_based_value`; `relations._BASE_*`). A whole number
   the prose restates right after it in another base, each base written (a subscript, "in binary", "in
   denary", "in hexadecimal", "the binary representation of"), is set against the numeral read in its
   base: a `base` check. Closing the class found that a base named only right after the first numeral
   reads two ways ("10 in binary is 1010" converts 10 into binary; "1010 in binary is 10" names the first
   numeral's base): reading it only as the first's failed the correct conversions written the first way
   (a false INT-SUBJ-001: "10 in binary is 1010", "100 in octal is 144"), so the check holds when either
   reading does, each numeral's digits allowing it (`Relation.alternative`).
9. **Rule `definite-integral`** (`parser._limits`, `_definite_integral`, `_signed_limit`,
   `_evaluation_bracket_check`; `nodes.Unsupported.lo`, `.hi`; `calculus.antiderivative`;
   `_Planner._definite`; `relations._limit_value`, `_limit_text`). A definite integral of a polynomial
   in one variable with whole-number limits is set against an evaluation bracket the answer states
   between the same limits (an `alg` check: the bracket's derivative against the integrand) or against
   a closed value (an `eq` check: the antiderivative the STEM pack forms by the power rule taken the
   other way, evaluated between the limits), and an evaluation bracket against a closed value (an `eq`
   check: its antiderivative at the upper limit minus at the lower one). Closing the class found that
   a limit with a minus sign ("∫₋₁¹", a subscript minus the lexer read as an unknown character) and
   limits written after "_" and "^" in plain text ("∫_0^1", the run ending at the caret's number) gave
   a relation with no check and no ST code at all: the lexer reads a subscript minus and a braced
   signed subscript as the sign of the subscript, the span finder reads a caret's number or braced
   number after an integral as its upper limit, and the limits reader takes a signed whole number.
10. **Rule `operand-precision` for given data** (`checks._given_exact`, `_rounding_bound`,
    `_operand_rounding_tau`): R12 above. Closing the class found that a stated side which is itself an
    expression of rounded numerals ("1/4.0 Ω + 1/6.0 Ω = 0.250 Ω⁻¹ + 0.167 Ω⁻¹") must add its own
    rounding (it has no half-width of its own in the band), and that earlier tests had written
    "4000 × 1.036⁵ = 4773.7406", a slip in the fourth decimal (4773.740074…) the rule now names; they
    write 4773.7401.
11. **Rule `ellipsis-rounding`** (`_Planner._ellipsis_restatement`, `_ellipsis_cut`;
    `relations._ellipsis_value`; `checks._res`, `_eq`; `lexer`; `parser`). A decimal written with its digits cut
    stands for any value from half a unit below its last written digit to a whole unit above it (the
    hull of the cut and the rounded readings): a value restated from it is set against it with the
    rounding the prose states (a `res` check), and a closed expression set equal to it is checked within
    it (an `eq` check). Closing the class found that a plain "…" or "..." after a decimal was punctuation
    that ended the run, so "8/3 = 2.66…" was read as a rounded 2.66 and failed (a false INT-SUBJ-001):
    the lexer reads it as the ellipsis marker LaTeX's `\ldots` is. Reading it so found three more of the
    class, each closed: the marker took what followed it as its operand, so "0.333… × 3 = 1" was read as
    the cut value restated as 1 and failed (a false INT-SUBJ-001; the marker after a decimal now takes
    nothing, and a cut value inside an expression is ST-UNDEC-001); a cut value on the left of the closed
    expression ("0.333… = 1/3", "2.66… = 8/3") was no relation in plain text and ST-UNDEC-001 in LaTeX
    (it is checked as on the right); and an approximate link ("8/3 ≈ 2.66…", "4787.58… ≈ 4788"), which
    the plain form had read as "≈ 2.66" and checked, would have been left ST-UNDEC-001 (it is checked
    with τ = 1/20, R2). A symbol set equal to a cut value ("x = 2.66…") is ST-UNDEC-001, as in LaTeX
    before and after (the plain form had bound the symbol to the digits as if rounded), and a cut value
    after a power beyond 12 stays ST-UNDEC-001.

On the 558 labelled corpus items the new readings change three: math-calc-2, stem-math-013 and
stem-math-014, a definite integral of a polynomial and its evaluation bracket each checked and holding
where both were ST-UNDEC-001 (math-calc-2's gold labels, which said undecided, say so now). On the
recorded round-7 STEM answers they add only checks that hold: ess-t13 the two counts of part (b),
maa-t13 the two evaluation brackets of part (c) (their two ST-UNDEC-001 gone), mai-t13 the restatement
of its cut value to the nearest euro, the place of that restatement and the computed value against
"135.36…" (the cut value's ST-UNDEC-001 gone; its power beyond 12 keeps its own). Remaining limits, stated: rule row-value reads
a clause that names exactly one row and one column and states the value, never a comparison, a change,
a processed quantity, a list of rows or a value under a condition, a hypothesis, a target, a modal verb
or a bound; rule named-component reads only a working whose values of the
component's dimension are all the request's; rule condition-result reads a condition with a unit of an
exact SI value, and a symbol with an earlier value under it; rule prose-base reads whole numbers with
both bases written; rule definite-integral reads only polynomials in one variable with whole-number
limits (a root, a function or a decimal limit stays ST-UNDEC-001); and rule ellipsis-rounding reads a
cut decimal set equal or approximately equal to a closed expression, or restated as a value, never a
cut integer, a cut sum, a cut decimal inside an expression or a symbol set equal to one; a plain "…"
written after a space ("8/3 = 2.66 …") is punctuation, as before this repair, so the decimal before it is
read as rounded.

## 31. STEM repair 11: readings added after the eleventh independent test

An eleventh independent test planted STEM faults on copies of the round-7 answers and found seven
problems, six of them in this front end. Correct working failed as an error when every operand was
whole and the result a rounded quotient written with "=" ("(92 − 18) ÷ 18 × 100 = 411%", "1,000 ÷ 3 =
333 items", "= 34% to 2 s.f."): exact mode gave h = 0 and τ = 0, and a rounding a line states for its
own result was read for restatements only. A Given one unit off the request's data in its last digit
held ("Given: r = 0.49 Ω." for 0.50 ohm): R7's band |w − b| ≤ h(b) + h(w) is inclusive. Part (b)'s
factorisation and roots in maa-t13 had no check: the request's "(a) … when t = 1" bound t for the
whole answer, so "6t − 3t² = 0" was an equation with nothing to solve. A function's value stated in
prose ("The velocity at t = 1 is v(1) = 4 m s⁻¹."), a wrong restatement of an inequality's solution
("n > 13.28…"), a wrong derivative (only ST-UNDEC-001), a wrong given substituted where no symbol is
bound ("$4500(1.036)^{11} = 6640.03$") and a base phrase opening the clause ("In binary, 1000 is
1111101100.") were each named by nothing. Each reading is fixed where it went wrong, for its whole
class, with a clean control for every new reading (`tests/stem/test_stem_repair11.py`); closing the
classes found more of each, below. The seventh problem, the knowledge pack's size, is the
overseer's: `docs/OVERSEER_DESIGN.md` section 42. The original translator's English, History and
generic readings are untouched. No ST code was added.

1. **Rule `exact-rounding`** (`checks._eq`, `_written_figures`, `_rational_form`, `_sub_evaluate`;
   R2 above). In exact mode (every operand and the stated value S exact, "="), τ is 0 and h is 0,
   unless S has two or more written significant figures, every trailing zero of a whole number
   counting, and closes rational written arithmetic (+, −, ×, ÷, integer powers, signs): then h is
   half a unit in S's last written digit. A whole computed value is still stated exactly ("17 × 23 =
   392" and "1000 ÷ 3 = 330" fail), one that is not whole may be stated to S's last digit ("(92 − 18)
   ÷ 18 × 100 = 411%", "1,000 ÷ 3 = 333", "29 ÷ 3 = 10" hold), and a single figure shows no rounding,
   so "7/3 = 2" still fails. The check's statement names the rule.
2. **Rule `result-rounding`** (`_Planner._result_rounding`; `checks._eq`). A rounding a line states
   for its own result, the value that closes its chain, right after it ("= 34% to 2 s.f.", "= 34%
   (to the nearest whole number)") or before it in its clause ("To 2 s.f., 1000 ÷ 3 = 330."), gives
   that result's h as R8 reads a restatement's (never less than half a unit in its last written
   digit), and rule rounded-digits sets the place the rounding names against the place the value is
   written to, as for a restatement. A rounding before the chain is its result's only when it opens the
   chain's clause, no number before it (`_rounding_opens_clause`): one that closes an earlier value's
   restatement ("…, so 5902 euros to the nearest euro, and $4000(1.036)^{12} = 6114.73$") is that
   value's. The first reading took it for the next chain's (a false INT-SUBJ-004 by rule rounded-digits
   on correct working, the arithmetic's band widened to half a euro), which the eleventh tester's own
   control found.
3. **Rule `given-data`** (`checks._giv`, `_sub_pairs`; R7 above). A value the request or a text
   supplied with it states, and a Given that restates one, is data, taken as written (R3): a Given
   value, or a value substituted for such a binding, matches it only when one of the two is the other
   rounded to its own last written digit, |w − b| ≤ max(h(w), h(b)), in SI with each half-width
   scaled by its unit's factor. "Given: r = 0.49 Ω." and "Given: r = 3.7%." fail against 0.50 ohm and
   3.6% (0.495 rounds to both, but the data are 0.50, not a rounding of it); "Given: r = 0.5 Ω.",
   "Given: r = 500 mΩ." and "9.81" for the request's 9.8 hold; "2.1 kg" substituted for m = 2.0 kg
   fails. The answer's own computed values keep R7's band (a carried result is rounded, and two
   roundings of it may differ by a unit). Closing the class found that `document._named_quantities`
   took the unit words of the quantity before a value as the next value's name ("two resistors of
   4.0 ohm and 6.0 ohm" had named 6.0 ohm "ohm and"): the name window starts after the previous
   quantity.
4. **Rules `part-condition` and `root-statement`** (`_Planner._given_in`, `_part_condition_note`,
   `_roots_candidate`, `_link`; `checks._reading_notes`). In mathematics a letter's values stated in a
   part, or in that part's question, are given in that part only (a science's symbol is a quantity
   whose value a later part may use, so the sciences read as before): a value the request states inside
   another part's question binds the letter there and nowhere else, so in another part the letter is
   an unknown of its equations, their steps and roots checked (maa-t13's part (b) "6t − 3t² = 0",
   "3t(2 − t) = 0", "t = 0 or t = 2": each checked and holding; "3t(2 + t) = 0" and "t = 0 or t = 3"
   fail). A root stated for an equation ("Factorising, rather than dividing by t, keeps t = 0." after
   "6t − 3t² = 0") leaves that equation as the relation the next line steps from, at the root's line
   for adjacency, so the factorisation after it is a step from the equation (before, the root became
   the premise and the factorisation followed from "t = 0" whatever its factors), and a root stated
   after a domain statement ("Both values lie in 0 ≤ t ≤ 3.") is checked against its equation, never
   as a step from the domain statement. Each step and root check names the reading it rests on in its
   statement ("t is an unknown of this part's equations: the request's t = 1 stands in the question of
   part (a), so it gives t that value in part (a) only (rule part-condition)", "the step is from the
   equation in s2.3, which the root stated in s2.4 solves … (rule root-statement)").
5. **Rule `function-value`** (`_Planner._function_values`, `_answer_functions`,
   `_defined_function_value`, `_request_functions`). A statement, any statement, that states the value
   of a function at a number for a function of one variable the answer defines before it ("v(t) = 6t −
   3t²", "Let f(x) = x² + 1.") or, failing that, the request defines, is an `eq` check of the
   function's expression at the written argument against the stated value or expression, the stated
   value's unit the one the request's prose states for the function's values: an error against the
   answer's own definition, a warning against the request's (that the letter is the request's
   function is a reading). Where the line's written arithmetic already evaluates the answer's function
   ("Then f(2) = 6."), that check is the check. Such a value is no relation a later line steps from
   (it had made "So v(2) = 6(2) − 3(2)² = 0." a failing step), and a letter neither defines as a
   function ("The ball is at k(2) = 5.") is no function value.
6. **Rule `inequality-solution`** (`_Planner._inequality_solution`; `Relation.cut_spans`; `checks._eq`).
   In mathematics, a solved form x ⋈ d (the letter alone, a closed value) that a step word joins to the
   relation before it in its part, where that relation is linear in the one letter (a·x + b ⋈′ c, a, b
   and c closed), states the bound the step solves for: an `eq` check of (c − b)/a against d, a value
   written with its digits cut ranging over [w − u/2, w + u] on either side (cut or rounded digits), τ
   = 0, whatever value the answer states for the letter elsewhere ("12n > 135.36…, so n > 11.28…" holds,
   "n > 13.28…" fails); a direction the division does not give ("so n < 11.28…") is a `cmp` step from
   the relation before, which fails.
7. **Rule `derivative`** (`parser._leibniz_read`, `_leibniz_parts`, `_leibniz_end`, `_latex`;
   `nodes.Unsupported.var`, `.order`, `.arg`, `.name`; `calculus.polynomial`, `derivative`;
   `_Planner._derivative`, `_function_of`). A derivative of a polynomial in one variable set equal to a
   polynomial in it, in Leibniz notation of any order ("d/dx (x²) = 2x", "d²s/dt² = 24t" after "s = 4t³
   − t", `\frac{dy}{dx}`) or as a letter with primes applied to a bracket ("f′(x) = 3x² − 2" after "f(x)
   = x³ − 2x"), is set against the derivative the STEM pack forms by the power rule (as for an
   antiderivative, never the engine) of the polynomial written after the operator, or of the function
   the letter stands for (the answer's own before the line, else the request's, then at warning
   severity): an `alg` check from the trivially true premise, so it holds iff the two polynomials
   agree. A derivative evaluated at a number with no formula of its own stated is set against the
   formed derivative at that number (an `eq` check: "f′(2) = 8" after "f(x) = x³" fails). A derivative
   set equal to a number where it is no constant ("dv/dt = 6" for v(t) = 6t − 3t², "f′(x) = 0" at a
   stationary point) states an equation in the variable to solve, and a derivative of anything else
   ("dN/dt = −λN", "d/dx (sin x) = cos x"), stays ST-UNDEC-001. A derivative line is never an algebra
   step from the line before it (such a step was never encodable).
8. **Rule `same-shape`** (`_Planner._same_shapes`, `_shape_slots`, `_answer_values_before`;
   `checks._GIV_RULES`). A line of working that puts, where the answer's other evaluation of the same
   expression (the same operators, units and numerals but one) writes a value the request states, a
   numeral neither the request nor the answer states before the line ("$4500(1.036)^{11} = 6640.03$"
   beside "$4000(1.036)^{12} = 6114.73$", the request's principal 4000 euros; "$4000(1.037)^{11}$" for
   its 3.6%, whose growth factor 1.036 the answer writes elsewhere) is set against that value: a `giv`
   check at warning severity. A per cent the request states is data in its decimal and in the growth
   and decay factors 1 ± the decimal, each written to the per cent's own precision (3.6% gives 0.036,
   1.036 and 0.964, each ± 0.0005). A line under a condition or a hypothesis ("if Kai had invested 4500
   euros instead") is not read.
9. **Rule `unbound-substitution`** (`_Planner._unbound_substitutions`; `checks._GIV_RULES`). A symbol
   the answer gives no value stands for one quantity: when the answer substitutes for it, elsewhere,
   the request's value of a quantity the request names with one value (part (c)'s "V = 12 V − (4.14 A
   × 0.50 Ω)" puts the internal resistance for r), any other value substituted for it ("R + r = 2.4 Ω +
   0.40 Ω") is set against that value: a `giv` check at warning severity (that the symbol stands for
   that quantity throughout is a reading). The tie must be one: a symbol the request's values tie to
   no one quantity (R for each of the two resistors in turn) and a value the working derives without
   stating it ("c = 0.0050 mol ÷ 0.0550 dm³", the total of the request's 50.0 cm³ and 5.0 cm³) are not
   read; a value the answer states before the line for the symbol is no substitution of it.
10. **Rule `prose-base`, a base phrase opening the clause** (`_Planner._prose_bases`;
    `relations._BASE_OPEN_RE`). A base the prose names once, opening the clause before both numerals
    ("In binary, 1000 is 1111101100.", "In base 2, 13 is 1101.", "Written in binary, 6 is 110."), is
    read as rule prose-base reads a base named only right after the first numeral: both ways, the
    check holding when either reading does.

Closing the classes found these too, each at its cause: rule exact-rounding at first gave every
whole S half a unit, which made "7/3 = 2" hold (a single figure shows no rounding: h stays 0); rule
same-shape at first built the per-cent forms with half a unit in the units place, which rule
given-data's max(h(w), h(b)) let any growth factor match ("1.037" held against 1.036), so those
forms carry the per cent's own precision; and rule
unbound-substitution at first set a derived total volume against the request's one value of its
symbol, so it reads a symbol only through a tie the answer itself writes. On the 558 labelled corpus
items the new readings change nine, each as labelled, from 1,924 checks and 96 findings to 1,934 and
91: math-calc-1, math-deriv-1 and a mutant of each (the derivative "f′(x) = 3x² − 2" a holding
power-rule check where it was ST-UNDEC-001; the gold labels of math-calc-1 and math-deriv-1 said
undecided and say checked now), stem-math-011 (its derivative "f'(x) = 6x + 2" and the value "6x + 2 =
0 ⇒ x = −1/3" solves for, both holding; its stationary point "f'(x) = 0" stays ST-UNDEC-001),
probe-M3-calculus-err and stem-math-012 (the planted wrong derivative "\frac{d}{dx}(3x^2 + 2x) = 3x +
2" an error on its claim; the chain's first link, a derivative set equal to a derivative, stays
ST-UNDEC-001), mai-func-1 (the function's value C(12), holding) and stem-phys-030 (the place its stated
rounding names, holding). On the recorded round-7 STEM answers they add only checks that hold (`docs/STEM_RESULTS.md`
section 10.7). Remaining limits, stated: rule exact-rounding reads rational written arithmetic only
(a root, a logarithm or a constant keeps h = 0 in exact mode); rule given-data reads the request's,
the supplied texts' and a Given's values, never the answer's computed ones; rule part-condition reads
a value the request states inside a part's question; rule function-value reads functions of one
variable whose expression has no other symbol, at a closed argument; rule inequality-solution reads a
relation linear in one letter; rule derivative reads polynomials in one variable; rule same-shape
reads an expression of written numerals that differs from the answer's other evaluation in one
numeral; rule unbound-substitution reads a symbol tied to one quantity by the answer's own
substitution of the request's value; and a power beyond 12 stays ST-UNDEC-001 (the reported
translator gap maths-finance-value).

## 32. STEM repair 12: readings added after the twelfth independent test

A twelfth independent test planted STEM faults on copies of the round-7 answers and found four
problems, three of them in this front end. An identity checked from the trivially true premise took
the request's value of its variable as a value it substitutes ("bindings included: t"), so a wrong
derivative whose stated side keeps the variable the formed side lacks ("Also d/dt (6 − 6t) = −6t."
beside maa-t13's "(a) … when t = 1") was decided at that one value and held: ENTAILED, satisfied,
no finding, a failure shown as a success. A hexadecimal numeral with letter digits in prose ("In
hexadecimal, 1000 is 3E9.", "3E9₁₆", "In base 16, …", "1000 in denary is 3E9 in hexadecimal.",
"The hexadecimal number 3E9 is 1000 in denary.") was no number to the front end, so the
restatement had no check. And a value after ", which is about" or ", about …" right after the
chain its line closes ("= 2.67 A, which is about 2.6 A", "= 37.7%, about 37%") was no restatement,
so a wrong rounding had no check. Each reading is fixed where it went wrong, for its whole class,
with a clean control for every new reading (`tests/stem/test_stem_repair12.py`); closing the
classes found more of each, below. The fourth problem, a circular translation in affine or scaled
form, is the overseer's: `docs/OVERSEER_DESIGN.md` section 43. The original translator's English,
History and generic readings are untouched. No ST code was added.

1. **Rule `identity-variable`** (`relations.Relation.identity`; `checks._step`). An identity the
   pack checks from the trivially true premise (a derivative against the one the power rule forms,
   an antiderivative by its derivative, a definite integral's evaluation bracket by its
   antiderivative, a Given function against the request's function, a factorisation in one chain)
   is stated for every value of its own variables: the planner records them on the relation, and
   the step takes no binding and no formula for them, so they stay free and the engine decides the
   identity for every value of them. The check's statement says so when the side the pack forms
   lacks the variable ("an identity, stated for every value of t: no binding or formula of it is
   included, so it is decided for every value (rule identity-variable)"). "d/dt (6 − 6t) = −6t",
   "d/dt (5t + 2) = 5t", "∫4t dt = 4t", "∫₀¹ 4t dt = [4t]₀¹" and "∫(6t − 3t²) dt = 6 − 6t" fail
   as errors and "Given: v(t) = 3." as a warning, with or without a request that gives t a value;
   their right forms hold. Every other step from a stated relation binds the values it
   substitutes, as before (ph-t13's "1/R = 1/4.0 Ω + 1/6.0 Ω": "bindings included: R_1, R_2"), and
   a constant the identity does not quantify may still take its value.
2. **The antiderivative's statement** (`relations._antiderivative`; `checks._step`). An
   antiderivative's check states what it compares, as a derivative's does ("compared: an
   antiderivative: the derivative of the stated antiderivative (formed by the STEM pack by the
   power rule, not by the engine) against the integrand, for every value of t (rule
   antiderivative)"); before, it said only "the algebraic step", so its statement named no
   variable (the overseer's rule identity-statement reads the identity's variable there).
3. **Rule `prose-base`, numerals with letter digits** (`relations._HEX_WORD_RE`, `_hex_words`,
   `_hex_word_pairs`, `_based_value`; `_Planner._prose_bases`). In a computer-science answer a
   numeral of digits and the capital letters A to F, at least one letter ("3E8", "FF", "1F4"), or of
   digits and small letters with at least one of each ("3e8", "1f4": never a word such as "face",
   "be" or "a"), with no base marker, is read in base 16 where the words beside it name that base:
   right before it ("The hexadecimal number 3E9"), right after it ("3E9 in hexadecimal"), or a base
   phrase opening the clause ("In hexadecimal, 1000 is 3E9.", "In base 16, …", "In hex, 26 is
   1B."), never as decimal and never where nothing names its base ("The largest byte value, 255,
   is FE." is not read). A numeral the lexer reads in e-notation whose characters are all
   hexadecimal digits ("3E9") is that hexadecimal numeral there. A numeral with a base marker keeps
   its own base in both readings of a phrase opening the clause, so "In hexadecimal, 1000 is
   3E9₁₆." names the second numeral's base (before, the phrase was read as the first's only, the
   two came out in one base and nothing was planned).
4. **Rule `prose-base`, the two false failures closing the class found** (`_Planner._worded_base`,
   `_hex_written`, `_link`; `_BASE_OPEN_RE`). A whole number set equal with "=" to a numeral whose
   base the words right after it name, its clause ending there ("1000 = 3E8 in hexadecimal.",
   "1000 = 1111101000 in binary.", "255 = FF in hexadecimal."), is a base conversion of the two
   numerals, each in its own base: before, it was written arithmetic on the numerals read as
   decimal ("3E8" as 3 × 10⁸), so correct working failed as an error, and letters alone ("FF") were
   an equation in the unknown F. A base phrase opening the clause is read as the opening phrase it
   is with no comma ("In binary 1000 is 1111101000.", "In octal 64 is 100.") and before "the
   number" ("In hexadecimal, the number 1000 is 3E9."): before, with no comma, the base word was
   read as the first numeral's ("binary 1000", as in "the binary number 1000"), so correct working
   failed.
5. **Rule `inline-restatement` after an approximation word** (`relations._INLINE_RESTATE_RE`,
   `_INLINE_CONNECTIVE_RE`, `_results`; `checks._res`, `_APPROX_BEFORE_RE`; `tolerance.tau_for`, R2
   and R8 above). A value after one of the connectives (", so", ", which is", ", i.e.", ", that
   is", ", or", ", giving") followed by an approximation word ("about", "approximately",
   "approx.", "roughly", "around", "nearly", with "equal to" after it or not), after ", about"
   and the others alone, after a rounding verb (", which rounds to", ", rounded to", "rounds up
   to") or in brackets after an approximation word ("= 2.67 A (about 2.7 A)"), with or without a
   rounding the prose states, restates the chain its own statement closes before it: a `res`
   check, the approximation word naming the restated value's rounding, with no τ (R8: "= 2.67 A,
   which is about 2.6 A", "= 2.67 A, about 2.6 A to 2 s.f." and "= 37.7%, about 37%" fail, "=
   2.67 A, which is about 2.7 A" holds; the detail says "τ = 0 (a restated result: the
   approximation word before it names its rounding, R8), on the line of working it restates (rule
   inline-restatement)"). The restatement check has always banded a restated value with no τ
   (`_res` passes τ = 0); R2 and `tau_for` now say so too, since "1/20 for ≈/about, any check"
   read otherwise. A value after an approximation word that no chain of its own statement closes
   before ("So each photon carries 4.0 × 10⁻¹⁹ J, which is about 2.5 eV.": a prose quantity, not a
   chain, stands before the connective) is no inline restatement, and a value after one of the
   connectives read before keeps that reading whatever stands before it ("The power is 16.4 W, so
   16 W to 2 s.f.": rule rounding-cue's).

Closing the classes found these too, each at its cause: the first reading of the approximation
connectives took the labelled corpus item stem-phys-029's "…, which is about 2.5 eV" for an inline
restatement of no chain, so its check was lost (a chain of its own statement is required now); the
first repair of that dropped the old connectives' reading with it, so a test's "The power is 16.4
W, so 16 W to 2 s.f." lost its rounding-cue check (the requirement applies to the new forms only);
and the equation form "1000 = 3E8 in hexadecimal." first read the words after the numeral at the
document's offsets rather than the statement's, so it held alone and failed inside an answer (the
statement's own text is read). On the 558 labelled corpus items and the recorded round-7 STEM
answers the new readings add no check and change no outcome; maa-t13's two recorded antiderivatives
state what they compare now (`docs/STEM_RESULTS.md` section 10.8). Remaining limits, stated: rule
identity-variable reads the identities the pack plans from the trivially true premise; letter
digits are read in computer-science answers only; a list of restatements in one clause ("In
hexadecimal, 1000 is 3E8 and 255 is FF.", "1000 is 1111101000 in binary and 3E8 in hexadecimal."),
a base named in brackets ("1000 (denary) is 3E8 (hexadecimal)") and a base named for the numeral
before "=" ("1000 in hexadecimal = 3E8") are not read, in any base; and an approximation word is read
after the connectives listed, on the line of the chain it restates.

---

## 33. Detection fixes from the end-to-end simulation (run1)

(Numbered section 21 on the development branch; the overseer build's STEM repairs took sections 21 to 32 first, so the translator merge that joined them numbers it 33. References to "section 21" in records written before the merge, such as dated arena reports, mean this section.)

The end-to-end simulation of the website-to-backend flow (sixteen specialists, the arena harness on
their genuine answers) left six injected faults unnamed. Each was traced to its cause; the answers
are kept as test data (`tests/channel/data/e2e_run1_material.json`) and every fix is pinned by
`tests/stem/test_e2e_run1_detection.py`. All six are now named, each as the harness injects it (the
injection is the base one; 33.3), and none is excused: an injection no finding names is a miss.

### 33.1 Gaps in the checks

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

### 33.2 A harness defect (`scripts/arena`)

7. **The part label in the marker** (maa-e1a substitution: `(b) P(t + 1) = P₀e^(k(t + 1))` →
   `P(t + 4)`). The marker kept the part label "(b) ", which no claim carries, so no injected claim
   was found; it now leaves a part label out as it leaves a mark annotation out, and m3.1 carries it.
   With the model evaluation (item 5) the injection is named on m3.1.

### 33.3 A rule withdrawn: no injection is excused

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

### 33.4 Tests changed

- `tests/fixtures/stem/corpus/stem-math-020.json` (and its copy in `tests/stem/data/stem_corpus.json`):
  the fractional-power fault `16^(3/4) = 16 × 3/4` was expected as undecided (ST-PARSE-001 or
  ST-UNDEC-001); the engine now refutes it (16^(3/4) is exactly 8), so it is expected as
  INT-SUBJ-001 alone from the arithmetic check (`FIXTURE_LABELS` in `tests/stem/data/corpus_items.py`
  pins the check kind `eq`), a stronger label. The fixture README records the change.
- `tests/stem/data/corpus_items_more.py` (`math-fracpow-1`): the relation
  `16^{3/4} = (\sqrt[4]{16})^3` is still named undecided with ST-UNDEC-001, now for the fourth root
  alone ('root of index 4'), since `16^{3/4}` is read; the corpus was rebuilt (two labels changed,
  558 items as before).
- `tests/stem/test_e2e_run1_detection.py`: the tests of the withdrawn rule (33.3), which asserted that
  the maa-e1a and mai-e1 substitutions were not applicable, are replaced by stricter ones: the mai-e1
  substitution is named INT-SUBJ-001 on m3.1, the verification's two probe misses are counted (27 of
  29), and with no finding allowed to name anything every injection of the round is a failure.
- The same file, after the second verification: the tests of the withdrawn injection change (33.3)
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

### 33.5 The join with the overseer build's STEM repairs

The translator merge that joined this section's fixes with the overseer build's STEM repairs (sections 21 to 32) found
two readings of one side that hid a check of the other or put a warning on correct work. Each is fixed at its cause and
pinned by `tests/stem/test_second_translator_merge.py`:

- Rule `restated-binding` (section 22) paired a value after "giving" with a relation between unknowns: once the thin
  space between digit groups was read (`$FV = -11\,491.11$`), the finance solver's setting `$C/Y = 12$` was taken for a
  restated binding and mai-e1 m13.1 got INT-SUBJ-004 on the genuine answer. A relation whose symbols have no stated
  value, binding or substitution in the scope is now no binding to restate; a relation whose symbols do have stated
  values is still read (the control: `v/t = 5.0 m s⁻²` after `v = 20 m s⁻¹` and `t = 4.0 s`).
- The count reader (section 21) took `2P₀` for the permutation count ⁿPᵣ, since a subscript digit passes Python's
  `str.isdigit`, so `P(0) = 2P₀` after the model `P = P₀e^(kt)` was named undecided and its model evaluation (33.1,
  `stem-mod`) never checked. A count's leading digits are ASCII digits only (`6P2`, `5C2` and `10C3` are still counts,
  as are `₅P₂` and `⁵C₂`); a coefficient before a subscripted letter (`2P₀`, `2C₀ = 0.10 mol dm⁻³`, `3P₁ + P₂`) is a
  product, and `P(0) = 2P₀` is now an evaluation the engine refutes (`stem-mod-2`, UNSATISFIABLE).

`tests/stem/test_stem_repair10.py`: the test that the cut value's recorded rounding holds and its power stays
undecided is rewritten to a stricter assertion. With the closed powers of 33.1 the merged front end decides
`1.003^60`, `1.003^132` and `1.003^144` beside `135.36`: it now requires those four checks, each holding, and no
ST-UNDEC-001 naming an integer power beyond 12.

## 34. The round-7 arena's STEM findings

The round-7 arena's STEM lenses (soundness, precision and parser safety) found readings that passed wrong working, failed
correct working or dropped a relation silently. Each is fixed where the reading went wrong, and
`tests/stem/test_round7_arena_fixes.py` pins every one with a clean control (a correct line that holds and a wrong one that
still fails). On the recorded round 7 the harness gives the same functional count (177 of 177) and, record for record, the
same STEM checks, statuses and findings as before the fixes.

- **Units read as written** (stem-soundness-1, `checks._as_written_consistent`). The reading as written (every unit a
  factor of 1) is admitted only when it is a consistent reading: when the units written on the computed side and on the
  stated value differ by a pure number other than 1, some bare factor written in the computation must supply it (`× 1000`,
  `× 60`, `× 3.6`, `× 100` for a per cent). So `3 × 2.0 kg = 6.0 g`, `2.0 kW × 3.0 = 6.0 W`, `300/400 = 0.75 %` and
  `80 × 25 % = 2000` are read in SI only and fail, while `2.5 kg × 1000 = 2500 g`, `300/400 × 100 = 75 %` and
  `120/4.0 = 30 km/h` (bare operands standing in km and h: a ratio with a dimension) keep both readings.
- **Exact integers in Mathematics and Computer Science** (stem-soundness-2, `checks._match_h`): an exact integer the
  answer states with no unit (`Let x = 3`) has h = 0, so a substituted 4 no longer matches it. A computed result keeps its
  half unit (it may be a rounding), and the request's data keep rule given-data.
- **Coefficients** (stem-soundness-3, `checks._non_coefficient_factors`): a symbol written in another order may stand
  opposite another factor of its product, but never opposite a numeral that writes the symbolic side's own coefficient
  (the 4 of `4x + 1`, the ½ of `½mv²`).
- **The AND dot** (stem-soundness-4): in Computer Science a full stop glued between single capitals or brackets is AND
  (`lexer._and_dot`: `A.B + A.C = A.(B + C)`); a relation glued by a full stop to a letter or a bracket on either side is a
  fragment and is withheld with ST-PARSE-001 (`checks._truncated_operand`), never decided.
- **Simultaneous equations** (stem-soundness-5, `relations._system_step`, `checks._sol_system`): consecutive equations of
  one part in the same two or more unknowns form a system when the words say so ("simultaneous", "system", "both
  equations", 'and' joining them in one statement, or the request stating both); no line of it is a step from the one
  before unless a connective says so, and the values the answer then states for its unknowns are planned as one `sol`
  check against every equation together: exact values in Form E, rounded ones in Form S over their R10 intervals, an
  unknown with no stated value free, never one equation with another stated value as a premise. Without such a word the
  line after an equation in two letters is a step, as before (`2x + y = 10`, then `2x = 10 − y`).
- **Approximation words** (stem-soundness-6, `tolerance.approx_word_before`, `approx_word_in`): a whole word only, and only
  directly before the relation (or between its two sides, `= about 6.3`); 'linearly', 'thoroughly', 'Around the bend' and
  'for about 3 s, and v = …' give no slack.
- **Degrees and radians** (stem-soundness-8, `checks._top_degrees`): an angle in degrees set against one in radians or a
  number (`30° = 0.524 rad`, `180° = π rad`) is compared in radians, a degree read as π/180 (its half-width scaled by a
  rational upper bound of π/180).
- **Trigonometric functions of a bare number** (stem-soundness-9, `checks._trig_angles`): read in degrees only when the
  request or the answer writes an angle in degrees and the answer never mentions radians, or when every such argument is a
  whole number beyond a full turn (`cos 60`); otherwise both readings, as before.
- **Roots with ±** (stem-soundness-10, `checks._step_conclusion`): a rounded value written `±1.41` is banded on both
  branches of the algebra step.
- **Roots on the next line** (stem-soundness-11): in Mathematics a root stated as a value on the line right after its
  equation claims the solution set as '⇒' does; roots on consecutive lines are one set; a line giving one root of several
  ("one root", "another"), a stated restriction, a root written as an expression and a formula's evaluation claim none.
- **Silent relations** (stem-soundness-12): a factorisation or expansion the words name ("Factorising", "Expand") is an
  identity checked for every value of its letters; a step to a chained inequality or to an inequality of an absolute value
  is named ST-UNDEC-001; a line opening with an absolute value is maths, not a pipe table; bits, bytes and the binary
  multiples (KiB, MiB, GiB) are units; a nuclear equation is named ST-UNDEC-001.
- **Restatements of another quantity** (stem-precision-1, `relations._restates_other_quantity`): a whole number with no
  unit after a chain whose value is no whole number restates it only when the clause between the cue and the value names
  nothing the chain's statement does not ('so the degrees of freedom are 3' after a χ² sum and 'so the loan lasts 60
  months' after a monthly rate are no restatements; 'Therefore the answer is 6' after '15/3 = 5', 'So there are 4
  half-lives' after '24/8.0 = 3' and a per cent still are).
- **Units of the substitution** (stem-precision-2 and -3): a bare substituted value also matches its binding converted to
  another unit of its dimension that the line's other values are written in (`checks._rescale_factors`: `V = 25.0 cm³` put
  in as 0.0250 beside `mol dm⁻³`), and a substitution whose symbols are bound in units with an SI factor other than 1 is
  offered the SI reading (`Pt = 2200 × 4.5 × 60` with `t = 4.5 min`).
- **Compound quantities** (stem-precision-5, `units.compound_part`): adjacent numeral and unit pairs of one dimension,
  each unit strictly smaller (`4 min 30 s`, `1 kg 250 g`, `1 h 2 min 3 s`), are one quantity, the sum of its parts, read in
  SI only.
- **A bracketed per cent after a value** (stem-precision-6): `0.870 (87%)` restates the value; it is no factor.
- **Comparisons stated false** (stem-precision-8, `relations._stated_false`): '2 <= 1, which is false', '5 > 8 is false',
  '(2 <= 1) fails' claim the negation, which is checked (its statement names the relation decided).
- **Count nouns** (stem-precision-9): a sign after a numeral and the noun it counts (`4 categories − 1 = 3`) is binary; the
  relation read from the sign is withheld with ST-PARSE-001.
- **Nibbles** (stem-precision-10): a binary or hexadecimal numeral in groups of four (or eight) digits ending in its base
  subscript (`1011 0110₂`) is one based numeral.
- **Superscript runs** (parser-safety-1): a run of superscript digits beyond the numeral bound (30 digits) is ST-LIM-001 on
  its span before any conversion (lexer, unit reader, parser); the rest of the answer is still read.

Two fixes need code outside `stem/` and were handed to their owners: STEM claim ids qualified with the agent
(combinator-faults-9, `adapters/stem_specialist/parser.py`) and an emptied STEM document reported at error severity
(parser-safety-1's second part, `branches/stem_pack.py`; the front end emits no error-severity finding by design). The
second is applied: `StemPack` adds the hub's PACK-INTERNAL-001 (error) beside ST-INTERNAL-001 when a report is left with no
STEM check by an internal failure (`tests/branches/test_r7_handoff_stem_pack.py`).

`tests/stem/test_checks_safety.py::test_too_many_readings_is_st_parse_002` is rewritten to a stricter assertion: its old input
(`sin(30)`, now read in degrees only) is asserted decided with its three readings, and the bound of four readings is
exercised with an argument read both ways (`sin(0.5)`).
